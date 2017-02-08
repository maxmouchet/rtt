# Traceroute Path Analysis
This documentation explains how we:
* translate IP path to ASN path;
* detect change in IP Forwarding Pattern (IFP);

## Usage
```
$ python path_analysis.py
```
The script will read all the traceroute measurement json files in [data/](../data) and produces
json files with the same names in the [data/path_analysis/](../data/path_analysis) folder
according to the __dir__ section in [config](../config).
__path_analysis.log__ will be generated for debugging uses.

Functions are provides in [localutils/pathtools.py](../localutils/pathtools.py) to perform following tasks in a standalone
manner, and thus can be easily reused out side the scope of this project:
* query IP address info from various [auxiliary data](auxiliary_data.md) source;
* detect the presence of IXP in IPv4 IP path seen in traceroute;
* detect changes in IP forwarding pattern;

For example:
```python
import localutils.pathtools as pt

# example for querying IP address information
pt.get_ip_info('195.191.171.31')
# Addr(addr='195.191.171.31', type=101, asn=197345, ixp=IXP(short='EPIX.Katowice', long='Stowarzyszenie na Rzecz Rozwoju Spoleczenstwa Informacyjnego e-Poludnie', country='PL', city='Katowice Silesia'), desc=None)
pt.get_ip_info('192.168.0.1')
# Addr(addr='192.168.0.1', type=104, asn=None, ixp=None, desc='private')

# example for translating IP path to ASN path
ip_path = ["10.71.6.11", "194.109.5.175", "194.109.7.169", "194.109.5.2", 
           "80.249.209.150", "72.52.92.213", "72.52.92.166", "184.105.223.165", 
           "184.105.80.202", "72.52.92.122", "x", "216.218.223.26", "130.152.184.3", 
           "x", "x", "x", "x", "x", "x"]
enhanced_hops = [pt.get_ip_info(hop) for hop in ip_path]
asn_path = pt.remove_repeated_asn([hop.get_asn() for hop in pt.insert_ixp(pt.bridge(enhanced_hops))])
# ['private', 3265, 'AMS-IX', 6939, 226, 'Invalid IP address']

# example for detecting IFP change
def print_seg(seg):
    for i in seg:
        print i

paris_id = [2, 3, 4, 5, 6, 0, 1,
            2, 3, 4, 5, 6, 0, 1,
            2, 3, 4, 5, 6, 0, 1,
            2, 3, 4, 5, 6, 0, 1,
            2, 3, 4, 5, 6, 0, 1]
# for the brevity of demonstration, each character stands for an IP path
paths = ['b', 'b', 'c', 'b', 'b', 'a', 'b',
         'b', 'a', 'a', 'k', 'b', 'a', 'b',
         'b', 'a', 'a', 'b', 'b', 'a', 'b',
         'b', 'a', 'a', 'b', 'b', 'a', 'b',
         'b', 'a', 'a', 'b', 'k', 'a', 'b']
seg = pt.ip_path_change_split(paris_id, paths, 7)  # 7 because 7 different Paris ID in all
print_seg(seg)
"""
Should expect:
(0, 2, pattern={0: None, 1: None, 2: 'b', 3: 'b', 4: 'c', 5: None, 6: None})
(3, 9, pattern={0: 'a', 1: 'b', 2: 'b', 3: 'a', 4: 'a', 5: 'b', 6: 'b'})
(10, 10, pattern={0: None, 1: None, 2: None, 3: None, 4: None, 5: 'k', 6: None})
(11, 31, pattern={0: 'a', 1: 'b', 2: 'b', 3: 'a', 4: 'a', 5: 'b', 6: 'b'})
(32, 32, pattern={0: None, 1: None, 2: None, 3: None, 4: None, 5: None, 6: 'k'})
(33, 34, pattern={0: 'a', 1: 'b', 2: None, 3: None, 4: None, 5: None, 6: None})

"""
pt.ifp_change(seg, len(paris_id))
# [0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 0]
```

## Output
Each json file in [data/path_analysis/](../data/path_analysis) follows the following structure:
```
{
    probe id (int):{
        "epoch": list of int; timestamps for each measurement,
        "ip_path": list of list of string; [[hop1, hop2,...],...],
        "asn_path": list of list of mixed type (int/string); [[ASN1, ASN2,...],...],
        "as_path_change": list of int; same length as "epoch" list, 1 for momement of change, otherwise 0,
        "ifp_simple": list of int; IP Forwarding Pattern (IFP) change detected with simple method; 0,1 as "as_path_change",
        "ifp_bck": list of int; IFP change detected with backward extension heuristic,
        "ifp_split": list of int; IFP change detected with further split and merge on top of backward extension
    }
}
```

## IP to ASN path
Trivial as the task may sound, IP to ASN path translation requires actually quite a lot special attentions,
apart from the third-party IP. (My personal view is that third-party IP has in fact relatively limited impact since 
1/only a small portion of the traceroutes are concerned according to previous studies, reference to be added;
2/ modern equipments tend to be implemented in a way that the response IP/interface being the same as the one that receives the packet, reference to be added.)

We take care of two issues in this work:
* how to handle reserved IPs, including private IP;
* how to detect the presence of IXP.

As a matter of fact, some IXPs use reserved IP blocks for inter-connection. 
Hence these two issues are actually mingled with each other.

Our method is:

0. add the probe IP at the beginning (helps to remove private hops at the head of ip path later on);
1. get enhanced IP hop information, from [auxiliary data](auxiliary_data.md) collected in this work;
  1. check if an IP is an [IXP interconnection address](auxiliary_data.md#ixp-related-data) used by member AS; (get info on IXP, and ASN of the member);
  2. else, check if an IP belongs to one of [prefixes used by certain IXP](auxiliary_data.md#ixp-related-data); (get info on the IXP);
  3. else, check if an IP belongs to one of [reserved IP blocks](auxiliary_data.md#reserved-ip-blocks); (get on the reserved purpose);
  4. else, check if an IP is announced by certain AS according to [BGP RIBs](auxiliary_data.md#routeview-bgp-ribs); (get info on ASN);  
2. once step 1 is down for each hop of a path, we remove hops in reserved IP blocks if they are directly surrounded by ASNs with know relationship
according to [CAIDA AS relationship inference](auxiliary_data.md#caida-as-relationship-inference);
(IXP prefixes are regarded transparent while IXP interco follows the ASN of the AS that uses it) 
3. detect the presence of IXP for IPv4 traceroutes (as IXP related info is only available in IPv4) using heuristics proposed by [traIXroute](https://github.com/gnomikos/traIXroute.git);
4. removed continuous repeated ASN in path.

NOTE: [traIXroute](https://github.com/gnomikos/traIXroute.git) does not try to remove reserved IPs even when it is possible.
This matters when such hop is next to IXP related addresses and prevents the detection.

## IP Forwarding Pattern change detection
RIPE Atlas uses Paris-traceroute in built-in traceroute.
In order to discover the IP path diversity, it uses rotating Paris IDs from 0 to 15. 
Each time, the Paris ID used is incremented by 1. When reaches 15, it comes back to 0.
This design has two major consequences in detecting IP-leve path changes:

1. Challenge: two neighbouring traceroute could naturally report two different IP paths due to load-balancing;
however that doesn't mean that any change in IP forwarding has ever taken place.
2. Benefit: it enlarges the chance of detecting changes in IP forwarding. If traceroute is locked on one single Paris ID,
it is possible that certain change alters only the path taken by the Paris IDs not used in the measurements, resulting false negative.

In order to detect IP path change not due to load balancing, we introduce the notion of IP Forwarding Pattern (IFP).
IFP is defined as the ensemble of mappings from **all** possible Paris IDs to IP paths correspondingly taken.
We use IFP to describe the forwarding status/configuration of a sub-sequence of IP path measurements.

When the IFPs attached to two neighbouring IP sequences differ, 
it indicates that there is a change in IP path other than those due to load-balancing.
Therefore, instead of detecting changes in bare IP path, we detect changes in IFP over a sequence of IP paths..

More formally:
```
{x -> y | x \in X, y \in Y}, where
X is the ensemble of Paris IDs and Y is the ensemble of IP paths.
```


```
# Example of Paris ID and path sequences in time

# s is sequence of Paris ID
# index     0  1  2  3  4  5  6
S =        [2, 3, 4, 5, 6, 0, 1,
            2, 3, 4, 5, 6, 0, 1,
            2, 3, 4, 5, 6, 0, 1,
            2, 3, 4, 5, 6, 0, 1,
            2, 3, 4, 5, 6, 0, 1]

# t is sequence of IP path
# for the brevity of demonstration, each character stands for an unique IP path
# index     0  1  2  3  4  5  6
T =        [b, b, c, b, b, a, b,
            b, a, a, k, b, a, b,
            b, a, a, b, b, a, b,
            b, a, a, b, b, a, b,
            b, a, a, b, k, a, b]
```

For the above example , we have `X = Unique(S) = {x| 0<= x < 7, x \in Z}` for all potential IFPs.
In the case of Atlas built-in traceroute, X would be 
```
X = { x | 0 <= x < 16, x \in Z}.
```

A mapping must be defined for each Paris ID in `X`  in an IFP, even though the underlying path sequence segment
doesn't cover all of them.
For example, the IFP for the first three IP path in the given example `S_{0:2}, T_{0:2}` would be:
```
{0->\iota, 1->\itoa, 2->b, 3->b, 4->c, 5->\iota, 6->\iota}
```
`\iota` is a wild card IP path element, i.e. `\iota = x, for \all x \in X`.
`\iota` is set for all the Paris ID that doesn't have a mapping definition according to the given path sequence segment.

We call an IFP `f` is **complete** if:
```
x -> \iota \not in f, for \all x \in X
```

Apparently an IFP can't not span over an arbitrary length of IP paths.
For example, it is not possible to define an IFP for `S_{0:8}, T_{0:8}`. 
Because for Paris ID 1, it has different IP path mappings, `b` and `a`.
And we can assume that from `s_8, t_8` a different routing scheme, e.g. a different IGP configuration, 
AS path change, etc. has taken place, as IFP changes.

More formally, we define that two IFPs `f1 and f2` are **different** if (only applicable to IFP with same X):
```
f1 \nsim f2, if exisits x \in X, f1(x) \neq f2_(x);

```
`f1` and `f2` are compatible if:
```
f1 ~ f2, if for \all x \in X, f1(x) = f2(x).
```

We intend to cut a IP path sequence along with Paris ID into segments, where:

* each segment follows one single IFP;
* two neighbouring segments follow different IFPs.

Such cut is not unique. We seek to identify those are most reasonable in the context of networking.


### Forward inclusion
A straightforward way of detecting IFP changes in IP path sequences along side with Paris ID is to construct segments
following a same IFP by adopting compatible IP path one by one, i.e. forward inclusion. 
Till the compatibility test failed, a new segment is started with a new IFP.
The beginning of each resulted segment is then when IFP change happens. Here below the procedure in pseudo code:
```
Algo: forward_inclusion
InPut: S, T                                     # S is sequence of Paris ID, T is sequence of corresponding IP path
OutPut: O                                       # O is sequence of path segments

1:  seg.begin <- 0                              # the begining index of a segment in S and T
2:  seg.end <- 0                                # the end index of a segment in S and T
3:  seg.f <- {x -> \iota | x \in Unique(S)}     # IFP of the segment
4:  for s, t, path \in e(S, T):
5:      if f(s) = t:
6:          f(s) <- t
7:          seg.end <- index of t
8:      else:
9:          append seg to O
11:         seg.begin <- index of t             # create new segment
12:         seg.end <- index of t
13:         seg.f <- {x -> t if x = s else x -> \iota | x \in Unique(S)}
14: if (begin, end, f) not in O:                # in case leaving the for loop while still inside a segment
15:     append seg to O
16: return O
```

If we take the example seen above, which is the same [usage](path_analysis.md#usage) section, we'd be expecting result as the following:
```python
seg = pt.ip_path_change_simple(paris_id, paths, 7)
print_seg(seg)
"""
(0, 7, pattern={0: 'a', 1: 'b', 2: 'b', 3: 'b', 4: 'c', 5: 'b', 6: 'b'})
(8, 16, pattern={0: 'a', 1: 'b', 2: 'b', 3: 'a', 4: 'a', 5: 'k', 6: 'b'})
(17, 31, pattern={0: 'a', 1: 'b', 2: 'b', 3: 'a', 4: 'a', 5: 'b', 6: 'b'})
(32, 34, pattern={0: 'a', 1: 'b', 2: None, 3: None, 4: None, 5: None, 6: 'k'})
"""
```

### Backward extension
With the forward inclusion, path sequence segments following a same IFP are developed incrementally in a forwarding direction 
as the IP path sequence is presented in time.
The drawback of this approach is evident. It potentially delays the detection of actually IFP changes, as once a new segment begins it always
has the chance to fill up all the Paris IDs.

If we look at the second segment `S_{8:16}, T_{8:16}` in the above example, 
we notice that all the IP paths starting from `S_{10}, T_{10}`, i.e. k, (exclusive),
are all ready compatible with the next segment from 17 to 31.
```
  0    1    2    3    4    5    6
['b', 'b', 'c', 'b', 'b', 'a', 'b',
 'b',('a', 'a', 'k', 'b', 'a', 'b',  # 2nd segment marked in ()
 'b', 'a', 'a',)'b', 'b', 'a', 'b',
 'b', 'a', 'a', 'b', 'b', 'a', 'b',
 'b', 'a', 'a', 'b', 'k', 'a', 'b']
```
Therefore chances are that the third segment begins from 11 (right after path k) instead of 17.

One might argue that it is still theoretically correct that the 2nd segment from 8 to 16 represent a IP forwarding pattern
unique and different from its neighbours, which is true.

However, according to the nature of network engineering/previous study (add reference here), 
networks tend to have some stable configurations that lead to a few dominant paths over time. 
That is to say, deviation from dominant/popular IFP is generally short living, 
sometimes not even able to present in all the Paris IDs. 
(Note, Paris IDs is sequentially scanned from 0 to 15, 
which takes at least 450min (30min * 15) to go through all of them for RIPE Atlas built-in traceroute.)
This rule of thumb justifies the observation that the later part of 2nd segment should actually belong to 3nd segment, 
as the IFP of later segment is fully repeated at least once and lasts longer than the 2nd segment, thus more popular.

Basing on such understanding, we propose backward extension on top of forward inclusion,
which extends the segment backwardly if the later one is more popular among the two neighbouring segments.
The pseudo code is give below:
```
Algo: backward_extension
InPut: S, T                                             # S is sequence of Paris ID, T is sequence of corresponding IP path
OutPut: O                                               # O is sequence of path segments

1:  O <- forward_inclusion(S, T)
2:  for seg, next_seg \in O:
3:      if (next_seg.f is complete) and                 # the IFP of next_seg should fully repeated at least once
4:          (next_seg.length >= 2 * |Unique(S)|) and  
5:          (next_seg.length > seg.length):             # we always enlarge the presence of the more popular (even locally) IFP
6:          while Ture:
7:              if S_{seg.end} -> T{seg.end} \in next_seg.f:
8:                  next_seg.begin <- seg.end
9:                  seg.end <- seg.end -1
10:             else:
11:                 break
12:  return O
```

We take again the same example, and apply backward extension to it:
```python
seg = pt.ip_path_change_bck_ext(paris_id, paths, 7)
print_seg(seg)
"""
(0, 7, pattern={0: 'a', 1: 'b', 2: 'b', 3: 'b', 4: 'c', 5: 'b', 6: 'b'})
(8, 10, pattern={0: None, 1: None, 2: None, 3: 'a', 4: 'a', 5: 'k', 6: None})
(11, 31, pattern={0: 'a', 1: 'b', 2: 'b', 3: 'a', 4: 'a', 5: 'b', 6: 'b'})
(32, 34, pattern={0: 'a', 1: 'b', 2: None, 3: None, 4: None, 5: None, 6: 'k'})
"""
```

### Further split and merge
Backward extension improves the detection result but is still not good enough.
It still falls short in pinpointing the short deviations from major IFP.

Let's look again at the example. With human pattern recognition power and some
familiarity with the topic, we might easily spot that the path k in the 2nd
segment, i.e. `S_{10}, T{10}` is actually a short deviation from major pattern.
The beginning of 2nd segment together with the tail of 1st segment (enclosed by '|' in beneath illustration) 
actually match with the major pattern (IFP of 3rd segment) and makes them (concatenated) a more appropriate segmentation.
```
  0    1    2    3    4    5    6
['b', 'b', 'c',|'b', 'b', 'a', 'b',  # path sequence segment enclosed by | matches with major IFP
 'b',('a', 'a',|'k', 'b', 'a', 'b',  # 2nd segment marked in ()
 'b', 'a', 'a',)'b', 'b', 'a', 'b',
 'b', 'a', 'a', 'b', 'b', 'a', 'b',
 'b', 'a', 'a', 'b', 'k', 'a', 'b']
```

In order to achieve such finer localization of short deviation we further split segments
without fully repeated IFP after backward extension to extract sub-segments that matches one of the major patterns.
Then we check again for all the neighbouring segments if them can be merged to match with one of the major patterns.
Here below the pseudo code:
```
Algo: split_and_merge
InPut: S, T                                             
OutPut: O                                             

1:  O <- backward_extension(S, T)
2:  p <- {seg.f | seg \in O, seg.length > 2 * |Unique(S)| is complete, seg.f is complete}   # popular IFPs
3:  for seg in O:
4:      if 2 < seg.length < 2 * |Unique(S)|:
5:          E <- {i | seg.begin <= i.begin < i.end <= seg.end, \exisits f \in p, f ~ i.f}   # sub-segment matches with popular IFPs
6:          e <- {i | i \in E, i.length = MAX(1, MAX_{j \in E}(j.length))}                  # longest sub-segment have more than 2 paths
7:          if e \neq \emptyset:
8:              split seg by one arbirarty i \in e
9:  for seg, next_seg in O:
10:     if seg.length < 2 * |Unique(S)| and next_seg.length < 2 * |Unique(S)|:
11:         if seg.f ~ next_seg.f:
12:             merge_seg = seg \frown next_seg                                             # tentativly merge the two segments
13:             if {f | f ~ merge_seg.f, f \in p} \neq \emptyset:
14:                 merge seg, next_seg
15: return O
```

We apply this further refined method to the example and find the output now catches
those short deviations and is in accordance with human recognition.
```python
seg = pt.ip_path_change_split(paris_id, paths, 7)
print_seg(seg)
"""
(0, 2, pattern={0: None, 1: None, 2: 'b', 3: 'b', 4: 'c', 5: None, 6: None})
(3, 9, pattern={0: 'a', 1: 'b', 2: 'b', 3: 'a', 4: 'a', 5: 'b', 6: 'b'})
(10, 10, pattern={0: None, 1: None, 2: None, 3: None, 4: None, 5: 'k', 6: None})
(11, 31, pattern={0: 'a', 1: 'b', 2: 'b', 3: 'a', 4: 'a', 5: 'b', 6: 'b'})
(32, 32, pattern={0: None, 1: None, 2: None, 3: None, 4: None, 5: None, 6: 'k'})
(33, 34, pattern={0: 'a', 1: 'b', 2: None, 3: None, 4: None, 5: None, 6: None})
"""
```