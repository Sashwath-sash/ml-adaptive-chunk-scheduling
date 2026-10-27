#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

typedef struct { int id, size, host, path, stat, query, keylen; } Request;
typedef struct { int feature, left, right, leaf, missing; double split, value; } Node;
typedef struct { int id, queue, freq; uint64_t tick; unsigned char bytes[4096]; } Slot;
static void die(const char *s) { perror(s); exit(1); }
static double seconds(void) { struct timespec t; clock_gettime(CLOCK_MONOTONIC, &t); return t.tv_sec+t.tv_nsec*1e-9; }
static uint64_t marker(int id) { return ((uint64_t)(unsigned)id*0x9e3779b97f4a7c15ULL)^0x123456789abcdef0ULL; }
static int predict_early(const double *x,const Node *nodes,const int *off,int trees,
                         double base,double cutoff,const double *min_tail,const double *max_tail,
                         uint64_t *evaluated) {
    double raw=base;
    for(int t=0;t<trees;t++) {int root=off[t],position=root;
        while(!nodes[position].leaf) {const Node *n=&nodes[position];double v=x[n->feature];
            position=root+(isnan(v)?(n->missing?n->left:n->right):(v<=n->split?n->left:n->right));
        }
        raw+=nodes[position].value;
        (*evaluated)++;
        if(raw+min_tail[t+1]>cutoff+1e-12)return 1;
        if(raw+max_tail[t+1]<cutoff-1e-12)return 0;
    }
    return raw>=cutoff;
}
static int count_queue(const Slot *slots,int cap,int queue) {
    int count=0;for(int j=0;j<cap;j++)if(slots[j].id>=0 && slots[j].queue==queue)count++;
    return count;
}
static void s3_evict_main(Slot *slots,int cap,uint64_t *clocktick) {
    for(;;) {int victim=-1;uint64_t oldest=UINT64_MAX;
        for(int j=0;j<cap;j++)if(slots[j].id>=0&&slots[j].queue==2&&slots[j].tick<oldest){oldest=slots[j].tick;victim=j;}
        if(victim<0)die("S3 main empty");
        if(slots[victim].freq>0){slots[victim].freq--;slots[victim].tick=++*clocktick;}
        else {slots[victim].id=-1;return;}
    }
}
static int s3_evict_small(Slot *slots,int cap,int main_max,int *ghost,uint64_t *ghost_tick,uint64_t *clocktick) {
    int victim=-1;uint64_t oldest=UINT64_MAX;
    for(int j=0;j<cap;j++)if(slots[j].id>=0&&slots[j].queue==1&&slots[j].tick<oldest){oldest=slots[j].tick;victim=j;}
    if(victim<0)die("S3 small empty");
    if(slots[victim].freq>1) {
        int freed=0;
        if(count_queue(slots,cap,2)>=main_max){s3_evict_main(slots,cap,clocktick);freed=1;}
        slots[victim].queue=2;slots[victim].freq=0;slots[victim].tick=++*clocktick;
        return freed;
    }
    int g=-1;uint64_t go=UINT64_MAX;
    int present=0;for(int j=0;j<cap;j++)if(ghost[j]>=0)present++;
    if(present<main_max) {
        for(int j=0;j<cap;j++)if(ghost[j]<0){g=j;break;}
    } else {
        for(int j=0;j<cap;j++)if(ghost[j]>=0&&ghost_tick[j]<go){go=ghost_tick[j];g=j;}
    }
    if(g<0)die("S3 ghost slot");
    ghost[g]=slots[victim].id;ghost_tick[g]=++*clocktick;
    slots[victim].id=-1;
    return 1;
}
static void s3_insert(Slot *slots,int cap,int key,const unsigned char *buffer,int *ghost,uint64_t *ghost_tick,uint64_t *clocktick) {
    int small_max=(int)lround(cap*.1);if(small_max<1)small_max=1;
    int main_max=cap-small_max;
    while(count_queue(slots,cap,1)+count_queue(slots,cap,2)>=cap) {
        if(count_queue(slots,cap,1)>=small_max)s3_evict_small(slots,cap,main_max,ghost,ghost_tick,clocktick);
        else s3_evict_main(slots,cap,clocktick);
    }
    int new_queue=1;
    for(int j=0;j<cap;j++)if(ghost[j]==key){ghost[j]=-1;new_queue=2;break;}
    if(new_queue==2 && count_queue(slots,cap,2)>=main_max)s3_evict_main(slots,cap,clocktick);
    int slot=-1;for(int j=0;j<cap;j++)if(slots[j].id<0){slot=j;break;}
    if(slot<0)die("S3 no free slot");
    slots[slot].id=key;slots[slot].queue=new_queue;slots[slot].freq=0;
    slots[slot].tick=++*clocktick;memcpy(slots[slot].bytes,buffer,4096);
}
static int ghost_count(const int *ghost,int cap){int n=0;for(int j=0;j<cap;j++)if(ghost[j]>=0)n++;return n;}
static int ghost_find(const int *ghost,int cap,int key){for(int j=0;j<cap;j++)if(ghost[j]==key)return j;return -1;}
static void ghost_remove_oldest(int *ghost,const uint64_t *ticks,int cap){
    int victim=-1;uint64_t oldest=UINT64_MAX;
    for(int j=0;j<cap;j++)if(ghost[j]>=0&&ticks[j]<oldest){oldest=ticks[j];victim=j;}
    if(victim<0)die("ARC ghost empty");
    ghost[victim]=-1;
}
static void arc_replace(Slot *slots,int cap,int key_in_b2,int target,
                        int *b1,uint64_t *b1ticks,int *b2,uint64_t *b2ticks,uint64_t *clocktick){
    int t1=count_queue(slots,cap,1);
    int queue=(t1 && (t1>target || (key_in_b2&&t1==target)))?1:2;
    int victim=-1;uint64_t oldest=UINT64_MAX;
    for(int j=0;j<cap;j++)if(slots[j].id>=0&&slots[j].queue==queue&&slots[j].tick<oldest){oldest=slots[j].tick;victim=j;}
    if(victim<0)die("ARC replacement queue empty");
    int *ghost=queue==1?b1:b2;uint64_t *ticks=queue==1?b1ticks:b2ticks;
    int place=-1;for(int j=0;j<cap;j++)if(ghost[j]<0){place=j;break;}
    if(place<0)die("ARC ghost capacity");
    ghost[place]=slots[victim].id;ticks[place]=++*clocktick;slots[victim].id=-1;
}
static void arc_insert(Slot *slots,int cap,int key,const unsigned char *buffer,
                       int *b1,uint64_t *b1ticks,int *b2,uint64_t *b2ticks,
                       int *target,uint64_t *clocktick){
    int h1=ghost_find(b1,cap,key),h2=ghost_find(b2,cap,key);
    int t1=count_queue(slots,cap,1),t2=count_queue(slots,cap,2);
    int n1=ghost_count(b1,cap),n2=ghost_count(b2,cap);
    int new_queue=1;
    if(h1>=0){int step=n1>0?n2/n1:0;if(step<1)step=1;
        *target+=step;if(*target>cap)*target=cap;
        arc_replace(slots,cap,0,*target,b1,b1ticks,b2,b2ticks,clocktick);
        b1[h1]=-1;new_queue=2;
    }else if(h2>=0){int step=n2>0?n1/n2:0;if(step<1)step=1;
        *target-=step;if(*target<0)*target=0;
        arc_replace(slots,cap,1,*target,b1,b1ticks,b2,b2ticks,clocktick);
        b2[h2]=-1;new_queue=2;
    }else{
        if(t1+n1==cap){
            if(t1<cap){ghost_remove_oldest(b1,b1ticks,cap);
                arc_replace(slots,cap,0,*target,b1,b1ticks,b2,b2ticks,clocktick);
            }else{int victim=-1;uint64_t oldest=UINT64_MAX;
                for(int j=0;j<cap;j++)if(slots[j].id>=0&&slots[j].queue==1&&slots[j].tick<oldest){oldest=slots[j].tick;victim=j;}
                if(victim<0)die("ARC T1 empty");
                slots[victim].id=-1;
            }
        }else if(t1+n1<cap && t1+t2+n1+n2>=cap){
            if(t1+t2+n1+n2==2*cap)ghost_remove_oldest(b2,b2ticks,cap);
            arc_replace(slots,cap,0,*target,b1,b1ticks,b2,b2ticks,clocktick);
        }
    }
    int place=-1;for(int j=0;j<cap;j++)if(slots[j].id<0){place=j;break;}
    if(place<0)die("ARC no free cache slot");
    slots[place].id=key;slots[place].queue=new_queue;slots[place].tick=++*clocktick;
    memcpy(slots[place].bytes,buffer,4096);
}
int main(int argc,char **argv) {
    if(argc!=4 && argc!=6) { fprintf(stderr,"usage: %s test_trace.txt model.txt repeats [policy --sync]\n",argv[0]); return 2; }
    int only_policy=-1;
    if(argc==6) {
        if(strcmp(argv[4],"lru")==0) only_policy=0;
        else if(strcmp(argv[4],"second_touch")==0) only_policy=1;
        else if(strcmp(argv[4],"ml")==0) only_policy=2;
        else if(strcmp(argv[4],"two_queue")==0) only_policy=3;
        else if(strcmp(argv[4],"s3fifo")==0) only_policy=4;
        else if(strcmp(argv[4],"tiny_lfu")==0) only_policy=5;
        else if(strcmp(argv[4],"arc")==0) only_policy=6;
        else if(strcmp(argv[4],"hybrid_arc")==0) only_policy=7;
        else if(strcmp(argv[4],"hybrid_s3fifo")==0) only_policy=8;
        else { fprintf(stderr,"unknown policy\n");return 2; }
        if(strcmp(argv[5],"--sync")!=0) { fprintf(stderr,"expected --sync\n");return 2; }
    }
    FILE *f=fopen(argv[1],"r"); if(!f)die("trace open");
    int n,keys,hosts; if(fscanf(f,"%d %d %d",&n,&keys,&hosts)!=3)die("trace header");
    Request *req=calloc(n,sizeof(*req)); if(!req)die("requests alloc");
    for(int i=0;i<n;i++) { Request *r=&req[i];
        if(fscanf(f,"%d %d %d %d %d %d %d",&r->id,&r->size,&r->host,&r->path,&r->stat,&r->query,&r->keylen)!=7)die("trace row");
        if(r->id<0||r->id>=keys||r->host<0||r->host>=hosts)die("trace bounds");
    }
    fclose(f);
    f=fopen(argv[2],"r"); if(!f)die("model open");
    int trees,cap,total; double base,threshold;
    if(fscanf(f,"%d %lf %lf %d %d",&trees,&base,&threshold,&cap,&total)!=5)die("model header");
    Node *nodes=calloc(total,sizeof(*nodes)); int *off=calloc(trees,sizeof(*off));
    if(!nodes||!off)die("model alloc");
    int at=0;
    for(int t=0;t<trees;t++) { int count; if(fscanf(f,"%d",&count)!=1)die("tree size"); off[t]=at;
        for(int j=0;j<count;j++) { Node *d=&nodes[at++];
            if(fscanf(f,"%d %lf %d %d %d %lf %d",&d->feature,&d->split,&d->left,&d->right,&d->leaf,&d->value,&d->missing)!=7)die("node");
        }
    }
    if(at!=total)die("node count");
    fclose(f);
    double *min_tail=calloc(trees+1,sizeof(double)),*max_tail=calloc(trees+1,sizeof(double));
    if(!min_tail||!max_tail)die("bound alloc");
    for(int t=trees-1;t>=0;t--){double low=INFINITY,high=-INFINITY;
        int end=t+1<trees?off[t+1]:total;
        for(int j=off[t];j<end;j++)if(nodes[j].leaf){
            if(nodes[j].value<low)low=nodes[j].value;
            if(nodes[j].value>high)high=nodes[j].value;
        }
        if(!isfinite(low)||!isfinite(high))die("tree leaf bounds");
        min_tail[t]=low+min_tail[t+1];max_tail[t]=high+max_tail[t+1];
    }
    double cutoff=log(threshold/(1.0-threshold));
    char tmp[]="/tmp/cache-native-XXXXXX"; int writefd=mkstemp(tmp); if(writefd<0)die("mkstemp");
    if(posix_fallocate(writefd,0,(off_t)keys*4096)!=0)die("fallocate");
    for(int id=0;id<keys;id++) { uint64_t v=marker(id); if(pwrite(writefd,&v,sizeof(v),(off_t)id*4096)!=sizeof(v))die("pwrite"); }
    if(fsync(writefd))die("fsync");
    close(writefd);
    int readfd=open(tmp,O_RDONLY|O_DIRECT); if(readfd<0)die("direct open"); unlink(tmp);
    unsigned char *buffer=NULL; if(posix_memalign((void**)&buffer,4096,4096))die("aligned alloc");
    Slot *cache=calloc(cap,sizeof(*cache)); int *count=calloc(keys,sizeof(int)),*last=malloc(keys*sizeof(int)),*hostcount=calloc(hosts,sizeof(int));
    int *ghost=malloc(cap*sizeof(int)),*ghost2=malloc(cap*sizeof(int)),*frequency=calloc(keys,sizeof(int));
    uint64_t *ghost_tick=calloc(cap,sizeof(uint64_t)),*ghost_tick2=calloc(cap,sizeof(uint64_t));
    if(!cache||!count||!last||!hostcount||!ghost||!ghost2||!ghost_tick||!ghost_tick2||!frequency)die("state alloc");
    int repeats=atoi(argv[3]); if(repeats<1||repeats>100)die("repeats bounds");
    if(only_policy>=0) { puts("READY");fflush(stdout);if(getchar()==EOF)die("synchronization input"); }
    printf("{\"requests\":%d,\"keys\":%d,\"capacity\":%d,\"trees\":%d,\"threshold\":%.17g,\"repeats\":[",n,keys,cap,trees,threshold);
    uint64_t expected=0; int expected_set=0;
    for(int rep=0;rep<repeats;rep++) {
        if(rep)putchar(',');
        putchar('[');
        for(int p=0;p<(only_policy>=0?1:5);p++) {
            int policy=only_policy>=0?only_policy:(p+rep)%5; const char *name=policy==0?"lru":policy==1?"second_touch":policy==2?"ml":policy==3?"two_queue":policy==4?"s3fifo":policy==5?"tiny_lfu":policy==6?"arc":policy==7?"hybrid_arc":"hybrid_s3fifo";
            memset(cache,0,cap*sizeof(*cache)); for(int c=0;c<cap;c++)cache[c].id=-1;
            for(int c=0;c<cap;c++){ghost[c]=-1;ghost2[c]=-1;}
            memset(count,0,keys*sizeof(int)); memset(frequency,0,keys*sizeof(int)); memset(hostcount,0,hosts*sizeof(int)); for(int k=0;k<keys;k++)last[k]=-1;
            int misses=0,hits=0,arc_target=0; int prefix[3]={-1,-1,-1}; uint64_t digest=0,clocktick=0,tree_evals=0; double start=seconds();
            for(int i=0;i<n;i++) { Request r=req[i]; int pos=-1;
                if(policy==5){if(i&&i%4096==0)for(int k=0;k<keys;k++)frequency[k]/=2;frequency[r.id]++;}
                for(int c=0;c<cap;c++)if(cache[c].id==r.id){pos=c;break;}
                uint64_t v;
                if(pos>=0) { hits++;if(policy==4||policy==8){if(cache[pos].freq<3)cache[pos].freq++;}else if(policy==6||policy==7){cache[pos].queue=2;cache[pos].tick=++clocktick;}else{cache[pos].tick=(uint64_t)i+1;if(policy==3)cache[pos].queue=2;} memcpy(&v,cache[pos].bytes,sizeof(v)); }
                else {
                    misses++; if(pread(readfd,buffer,4096,(off_t)r.id*4096)!=4096)die("direct pread");
                    memcpy(&v,buffer,sizeof(v)); if(v!=marker(r.id))die("backing data mismatch");
                    int admit=policy==0 || policy==3 || policy==4 || policy==5 || policy==6 || (policy==1 && count[r.id]>=1);
                    if(policy==5){int victim=-1;uint64_t oldest=UINT64_MAX;int full=1;
                        for(int c=0;c<cap;c++)if(cache[c].id<0){full=0;break;}
                        if(full){for(int c=0;c<cap;c++)if(cache[c].tick<oldest){oldest=cache[c].tick;victim=c;}
                            if(frequency[r.id]<frequency[cache[victim].id])admit=0;}
                    }
                    if(policy==2||policy==7||policy==8) { double x[8]={ (double)(float)log1p(r.size), (double)(float)log1p(count[r.id]),
                        (double)(float)log1p(last[r.id]<0?n+1:i-last[r.id]), (double)(float)log1p(hostcount[r.host]),
                        (double)(float)r.path,(double)(float)r.stat,(double)(float)r.query,(double)(float)r.keylen};
                        admit=predict_early(x,nodes,off,trees,base,cutoff,min_tail,max_tail,&tree_evals);
                    }
                    if(policy==4) s3_insert(cache,cap,r.id,buffer,ghost,ghost_tick,&clocktick);
                    else if(policy==8&&admit) s3_insert(cache,cap,r.id,buffer,ghost,ghost_tick,&clocktick);
                    else if((policy==6||policy==7)&&admit) arc_insert(cache,cap,r.id,buffer,ghost,ghost_tick,ghost2,ghost_tick2,&arc_target,&clocktick);
                    else if(admit) { int victim=-1; uint64_t oldest=UINT64_MAX; int new_queue=0;
                        if(policy==3) {
                            new_queue=1;
                            for(int c=0;c<cap;c++)if(ghost[c]==r.id){ghost[c]=-1;new_queue=2;break;}
                            int recent=0; for(int c=0;c<cap;c++)if(cache[c].id>=0&&cache[c].queue==1)recent++;
                            if(new_queue==1 && recent>= (cap/4>0?cap/4:1)) {
                                for(int c=0;c<cap;c++)if(cache[c].id>=0&&cache[c].queue==1&&cache[c].tick<oldest){oldest=cache[c].tick;victim=c;}
                                int g=-1; uint64_t go=UINT64_MAX;
                                for(int c=0;c<cap;c++){if(ghost[c]<0){g=c;break;}if(ghost_tick[c]<go){go=ghost_tick[c];g=c;}}
                                ghost[g]=cache[victim].id;ghost_tick[g]=(uint64_t)i+1;
                            }
                        }
                        if(victim<0)for(int c=0;c<cap;c++)if(cache[c].id<0){victim=c;break;}
                        if(victim<0) { oldest=UINT64_MAX;
                            for(int c=0;c<cap;c++)if((policy!=3||cache[c].queue==2)&&cache[c].tick<oldest){oldest=cache[c].tick;victim=c;}
                        }
                        if(victim<0)die("no cache victim");
                        cache[victim].id=r.id; cache[victim].queue=new_queue; cache[victim].tick=(uint64_t)i+1; memcpy(cache[victim].bytes,buffer,4096);
                    }
                }
                digest^=v+0x9e3779b97f4a7c15ULL+(uint64_t)i;
                count[r.id]++;hostcount[r.host]++;last[r.id]=i;
                if(i+1==1024)prefix[0]=misses;
                if(i+1==2048)prefix[1]=misses;
                if(i+1==4096)prefix[2]=misses;
            }
            double elapsed=seconds()-start;
            if(expected_set && digest!=expected)die("policy checksum mismatch");
            expected=digest; expected_set=1;
            if(p)putchar(',');
            printf("{\"policy\":\"%s\",\"wall_seconds\":%.9f,\"hits\":%d,\"direct_reads\":%d,\"direct_bytes_requested\":%lld,\"tree_nodes_evaluated\":%llu,\"prefix_misses\":[%d,%d,%d],\"checksum\":\"%016llx\"}",name,elapsed,hits,misses,(long long)misses*4096,(unsigned long long)tree_evals,prefix[0],prefix[1],prefix[2],(unsigned long long)digest);
        }
        putchar(']');
    }
    puts("]}");close(readfd);free(buffer);free(cache);free(count);free(last);free(hostcount);free(ghost);free(ghost2);free(ghost_tick);free(ghost_tick2);free(frequency);free(req);free(nodes);free(off);free(min_tail);free(max_tail);
    return 0;
}
