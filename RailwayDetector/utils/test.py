import heapq

# 根据请求分配节点路由，并更新节点缓存和负载
def allocate(caches, loads, request):  
    heap = []
    
    # 计算当前请求下的n个节点对应的缓存命中长度
    for (i, cache) in enumerate(caches):
        MaxLength = 0
        for sequence in cache:
            Length = 0
            for j in range(min(len(request), len(sequence))):
                if request[j] == sequence[j]:
                    Length += 1
                else:
                    break
            
            if MaxLength < Length:
                MaxLength = Length

        # 将（-节点缓存长度，负载，节点编号）加入最小堆，并给出分配节点编号
        heapq.heappush(heap, (-MaxLength, loads[i], i))
    
    # 更新节点缓存和负载，最后返回节点编号
    _, _, id = heapq.heappop(heap)
    caches[id].append(request)
    loads[id] += len(request)
    return id


# 输入
N, M = map(int, input().split())
loads = list(map(int, input().split()))
caches = []

for i in range(N):
    _, *sequences = input().split()
    cache = []
    for sequence in sequences:
        sequence = list(map(int, sequence.split(",")))
        cache.append(sequence)
    
    caches.append(cache)

ids = []
for i in range(M):
    request = list(map(int, input().split()))
    id = allocate(caches, loads, request)
    ids.append(id)

print(*ids)
    




