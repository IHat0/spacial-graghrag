# =============================================================================
# PILLAR 2: SPATIAL GRAPHRAG & THE "DÉJÀ VU" SEED SYSTEM
# Full Benchmark Simulator — Sparse-by-Design, Lazy Local Subgraphs,
# Dijkstra vs A* with Real Heuristic, tracemalloc Peak Reporting
# =============================================================================

import networkx as nx
import random
import math
import time
import tracemalloc
import csv
import os
from typing import Dict, List, Tuple


class SpatialGraphRAG:
    """
    Hierarchical Spatial GraphRAG Simulator.
    Sparse-by-design: minimal node/edge attributes, lazy local subgraph loading.
    """

    def __init__(self, seed: int = 42):
        random.seed(seed)
        self.global_graph = nx.Graph()
        self.local_graphs: Dict[str, nx.Graph] = {}   # Lazy-loaded local subgraphs
        self.active_local_nodes: set = set()            # Currently loaded local nodes
        self.node_coords: Dict[str, Tuple[float, float, float]] = {}
        self.destroyed_nodes: set = set()
        self.lru_cache: List[str] = []                # LRU for local subgraph eviction
        self.max_local_cache = 3                        # Keep only 3 locals in RAM

    # -------------------------------------------------------------------------
    # PHASE A: "DÉJÀ VU" INITIALIZATION (Global Map)
    # -------------------------------------------------------------------------

    def generate_global_map(self, num_nodes: int = 100,
                            biome_types: List[str] = None) -> None:
        """Generate a sparse global map of high-level nodes."""
        if biome_types is None:
            biome_types = ['Forest', 'Mountain', 'Plains', 'Desert',
                           'River', 'Cave', 'Village', 'Ocean', 'Swamp', 'Tundra']

        for i in range(num_nodes):
            biome = random.choice(biome_types)
            node_id = f"{biome}_{i}"
            # Minimal attributes: type, status, coords (for A* heuristic)
            x, y, z = random.uniform(0, 1000), random.uniform(0, 100), random.uniform(0, 1000)
            self.global_graph.add_node(node_id,
                                       type='global',
                                       status='active',
                                       coords=(x, y, z))
            self.node_coords[node_id] = (x, y, z)

        # Sparse edges: spanning tree backbone + a few long-range connections
        nodes = list(self.global_graph.nodes())
        for i in range(1, num_nodes):
            parent = nodes[random.randint(0, i - 1)]
            child = nodes[i]
            dist = self._euclidean_dist(parent, child)
            self.global_graph.add_edge(parent, child, weight=dist)

        extra_edges = num_nodes // 10
        for _ in range(extra_edges):
            u, v = random.sample(nodes, 2)
            if not self.global_graph.has_edge(u, v):
                dist = self._euclidean_dist(u, v)
                self.global_graph.add_edge(u, v, weight=dist)

    def _euclidean_dist(self, u: str, v: str) -> float:
        """Euclidean distance between two nodes for edge weights and A* heuristic."""
        x1, y1, z1 = self.node_coords[u]
        x2, y2, z2 = self.node_coords[v]
        return math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2 + (z2 - z1) ** 2)

    # -------------------------------------------------------------------------
    # PHASE B: LOCAL DISCOVERY (Chunk Sub-Graphs)
    # -------------------------------------------------------------------------

    def enter_global_node(self, global_node: str) -> nx.Graph:
        """When agent arrives at a global node, lazily load its local subgraph."""
        if global_node in self.local_graphs:
            self._touch_lru(global_node)
            return self.local_graphs[global_node]

        # Evict oldest if cache is full
        if len(self.lru_cache) >= self.max_local_cache:
            oldest = self.lru_cache.pop(0)
            self._unload_local_subgraph(oldest)

        # Generate local subgraph on-demand
        local_g = self._generate_local_subgraph(global_node)
        self.local_graphs[global_node] = local_g
        self.lru_cache.append(global_node)

        for node in local_g.nodes():
            self.active_local_nodes.add(node)

        return local_g

    def _generate_local_subgraph(self, parent_node: str, num_local: int = 20) -> nx.Graph:
        """Generate a tight cluster of detailed local nodes."""
        local_g = nx.Graph()
        px, py, pz = self.node_coords[parent_node]

        local_types = ['Oak_Tree', 'Boulder', 'Iron_Vein', 'Cave_Entrance',
                       'Pond', 'Bush', 'Mushroom_Patch', 'Fallen_Log',
                       'Berry_Bush', 'Stream', 'Rock_Formation', 'Dirt_Path']

        local_nodes = []
        for i in range(num_local):
            ltype = random.choice(local_types)
            node_id = f"{parent_node}::{ltype}_{i}"
            lx = px + random.gauss(0, 5)
            ly = py + random.gauss(0, 2)
            lz = pz + random.gauss(0, 5)

            local_g.add_node(node_id,
                             type='local',
                             status='active',
                             parent=parent_node,
                             coords=(lx, ly, lz))
            self.node_coords[node_id] = (lx, ly, lz)
            local_nodes.append(node_id)

        # Dense local connections (mesh-like within chunk)
        for i in range(num_local):
            for j in range(i + 1, num_local):
                if random.random() < 0.3:
                    u, v = local_nodes[i], local_nodes[j]
                    dist = self._euclidean_dist(u, v)
                    local_g.add_edge(u, v, weight=dist)

        # Connect to parent global node (entry/exit)
        entry_node = random.choice(local_nodes)
        local_g.add_edge(parent_node, entry_node,
                         weight=self._euclidean_dist(parent_node, entry_node))

        return local_g

    def _unload_local_subgraph(self, global_node: str) -> None:
        """Unload a local subgraph from memory to maintain sparse footprint."""
        if global_node not in self.local_graphs:
            return
        local_g = self.local_graphs[global_node]
        for node in list(local_g.nodes()):
            if node != global_node:
                self.active_local_nodes.discard(node)
                if node in self.node_coords and '::' in node:
                    del self.node_coords[node]
        del self.local_graphs[global_node]

    def _touch_lru(self, global_node: str) -> None:
        """Move global_node to end of LRU list."""
        if global_node in self.lru_cache:
            self.lru_cache.remove(global_node)
            self.lru_cache.append(global_node)

    # -------------------------------------------------------------------------
    # PHASE C: THE "BROKEN BRIDGE" MUTATION (Dynamic Update)
    # -------------------------------------------------------------------------

    def sever_edge(self, u: str, v: str) -> bool:
        """Simulate L0 interrupt: destroy an edge."""
        if self.global_graph.has_edge(u, v):
            self.global_graph.remove_edge(u, v)
            return True
        for local_g in self.local_graphs.values():
            if local_g.has_edge(u, v):
                local_g.remove_edge(u, v)
                return True
        return False

    def mark_destroyed(self, node: str) -> None:
        """Mark a node as DESTROYED."""
        self.destroyed_nodes.add(node)
        if self.global_graph.has_node(node):
            self.global_graph.nodes[node]['status'] = 'DESTROYED'
        for local_g in self.local_graphs.values():
            if local_g.has_node(node):
                local_g.nodes[node]['status'] = 'DESTROYED'

    # -------------------------------------------------------------------------
    # PATHFINDING: Dijkstra vs A*
    # -------------------------------------------------------------------------

    def dijkstra_path(self, source: str, target: str) -> Tuple[List[str], float]:
        """Dijkstra shortest path — clean baseline, no heuristic."""
        try:
            path = nx.shortest_path(self.global_graph, source, target, weight='weight')
            length = nx.shortest_path_length(self.global_graph, source, target, weight='weight')
            return path, length
        except nx.NetworkXNoPath:
            return [], float('inf')

    def astar_path(self, source: str, target: str) -> Tuple[List[str], float]:
        """A* with real Euclidean heuristic using node coordinates."""
        def heuristic(u, v):
            return self._euclidean_dist(u, v)

        try:
            path = nx.astar_path(self.global_graph, source, target,
                                 heuristic=heuristic, weight='weight')
            length = nx.astar_path_length(self.global_graph, source, target,
                                          heuristic=heuristic, weight='weight')
            return path, length
        except nx.NetworkXNoPath:
            return [], float('inf')

    # -------------------------------------------------------------------------
    # TOKEN PAYLOAD: Context Efficiency
    # -------------------------------------------------------------------------

    def get_local_context(self, node: str) -> str:
        """Generate <50 token context for LLM query 'Where am I?'"""
        if node not in self.global_graph:
            return f"Unknown location: {node}"

        neighbors = list(self.global_graph.neighbors(node))
        active_neighbors = [n for n in neighbors
                            if self.global_graph.nodes[n].get('status') != 'DESTROYED']

        context = f"You are at {node}. Connected: {', '.join(active_neighbors[:5])}."
        return context

    def count_tokens(self, text: str) -> int:
        """Rough token count (English ~0.75 tokens per word)."""
        return int(len(text.split()) / 0.75)


# =============================================================================
# BENCHMARK FUNCTIONS
# =============================================================================

def benchmark_memory_footprint(target_nodes: int = 10000,
                               target_edges: int = 25000) -> Dict:
    """Metric 1: Memory Footprint. Target: < 15 MB."""
    print(f"\n[Benchmark 1] Memory Footprint: {target_nodes} nodes, {target_edges} edges")

    tracemalloc.start()
    rag = SpatialGraphRAG(seed=42)
    rag.generate_global_map(num_nodes=target_nodes)

    nodes = list(rag.global_graph.nodes())
    current_edges = rag.global_graph.number_of_edges()
    edges_to_add = target_edges - current_edges

    added = 0
    attempts = 0
    while added < edges_to_add and attempts < target_edges * 10:
        u, v = random.sample(nodes, 2)
        if not rag.global_graph.has_edge(u, v):
            dist = rag._euclidean_dist(u, v)
            rag.global_graph.add_edge(u, v, weight=dist)
            added += 1
        attempts += 1

    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    peak_mb = peak / (1024 * 1024)
    current_mb = current / (1024 * 1024)

    result = {
        'metric': 'Memory_Footprint',
        'target_nodes': target_nodes,
        'actual_nodes': rag.global_graph.number_of_nodes(),
        'actual_edges': rag.global_graph.number_of_edges(),
        'current_mb': round(current_mb, 4),
        'peak_mb': round(peak_mb, 4),
        'target_mb': 15,
        'passed': peak_mb < 15
    }

    print(f"  Current: {current_mb:.4f} MB | Peak: {peak_mb:.4f} MB | Target: <15 MB | {'PASS' if result['passed'] else 'FAIL'}")
    return result


def benchmark_query_latency(rag: SpatialGraphRAG,
                            test_nodes: int = 1000,
                            iterations: int = 200) -> Dict:
    """Metric 2: Query Latency. Target: < 2 ms."""
    print(f"\n[Benchmark 2] Query Latency: pathfinding over {test_nodes} nodes")

    if rag.global_graph.number_of_nodes() < test_nodes:
        rag.generate_global_map(num_nodes=test_nodes)

    nodes = list(rag.global_graph.nodes())[:test_nodes]

    # Warm-up
    for _ in range(10):
        u, v = random.sample(nodes, 2)
        rag.dijkstra_path(u, v)
        rag.astar_path(u, v)

    dij_times = []
    for _ in range(iterations):
        u, v = random.sample(nodes, 2)
        t0 = time.perf_counter()
        rag.dijkstra_path(u, v)
        t1 = time.perf_counter()
        dij_times.append((t1 - t0) * 1000)

    astar_times = []
    for _ in range(iterations):
        u, v = random.sample(nodes, 2)
        t0 = time.perf_counter()
        rag.astar_path(u, v)
        t1 = time.perf_counter()
        astar_times.append((t1 - t0) * 1000)

    dij_avg = sum(dij_times) / len(dij_times)
    astar_avg = sum(astar_times) / len(astar_times)
    dij_min = min(dij_times)
    astar_min = min(astar_times)

    best_algo = 'A*' if astar_avg < dij_avg else 'Dijkstra'
    best_avg = min(dij_avg, astar_avg)
    best_min = min(dij_min, astar_min)

    result = {
        'metric': 'Query_Latency',
        'test_nodes': test_nodes,
        'iterations': iterations,
        'dijkstra_avg_ms': round(dij_avg, 4),
        'dijkstra_min_ms': round(dij_min, 4),
        'astar_avg_ms': round(astar_avg, 4),
        'astar_min_ms': round(astar_min, 4),
        'best_algorithm': best_algo,
        'best_avg_ms': round(best_avg, 4),
        'best_min_ms': round(best_min, 4),
        'target_ms': 2,
        'passed': best_avg < 2
    }

    print(f"  Dijkstra: {dij_avg:.4f} ms avg | A*: {astar_avg:.4f} ms avg")
    print(f"  Best: {best_algo} @ {best_avg:.4f} ms avg | Target: <2 ms | {'PASS' if result['passed'] else 'FAIL'}")
    return result


def benchmark_mutation_latency(rag: SpatialGraphRAG,
                               detour_nodes: int = 50,
                               iterations: int = 200) -> Dict:
    """Metric 3: Mutation/Recalculation Latency. Target: < 5 ms."""
    print(f"\n[Benchmark 3] Mutation Latency: edge destroy + {detour_nodes}-node detour")

    nodes = list(rag.global_graph.nodes())[:detour_nodes * 2]
    mutation_times = []

    for _ in range(iterations):
        edges = list(rag.global_graph.edges())
        if len(edges) < 2:
            continue
        u, v = random.choice(edges)

        remaining = [n for n in nodes if n not in (u, v)]
        if len(remaining) < 2:
            continue
        source, target = random.sample(remaining, 2)

        t0 = time.perf_counter()
        rag.sever_edge(u, v)
        rag.dijkstra_path(source, target)
        t1 = time.perf_counter()

        mutation_times.append((t1 - t0) * 1000)

        # Restore edge for next iteration
        if not rag.global_graph.has_edge(u, v):
            dist = rag._euclidean_dist(u, v)
            rag.global_graph.add_edge(u, v, weight=dist)

    avg_ms = sum(mutation_times) / len(mutation_times) if mutation_times else 999
    min_ms = min(mutation_times) if mutation_times else 999

    result = {
        'metric': 'Mutation_Latency',
        'detour_nodes': detour_nodes,
        'iterations': len(mutation_times),
        'avg_ms': round(avg_ms, 4),
        'min_ms': round(min_ms, 4),
        'target_ms': 5,
        'passed': avg_ms < 5
    }

    print(f"  Avg: {avg_ms:.4f} ms | Min: {min_ms:.4f} ms | Target: <5 ms | {'PASS' if result['passed'] else 'FAIL'}")
    return result


def benchmark_token_payload(rag: SpatialGraphRAG, iterations: int = 100) -> Dict:
    """Metric 4: Token Payload Size. Target: < 50 tokens."""
    print(f"\n[Benchmark 4] Token Payload: LLM context efficiency")

    nodes = list(rag.global_graph.nodes())
    token_counts = []
    payloads = []

    for _ in range(iterations):
        node = random.choice(nodes)
        context = rag.get_local_context(node)
        tokens = rag.count_tokens(context)
        token_counts.append(tokens)
        payloads.append(context)

    avg_tokens = sum(token_counts) / len(token_counts)
    max_tokens = max(token_counts)
    min_tokens = min(token_counts)

    result = {
        'metric': 'Token_Payload',
        'iterations': iterations,
        'avg_tokens': round(avg_tokens, 2),
        'max_tokens': max_tokens,
        'min_tokens': min_tokens,
        'target_tokens': 50,
        'passed': max_tokens < 50,
        'sample_payload': payloads[0]
    }

    print(f"  Avg: {avg_tokens:.2f} tokens | Max: {max_tokens} tokens | Target: <50 | {'PASS' if result['passed'] else 'FAIL'}")
    print(f"  Sample: '{payloads[0]}'")
    return result


# =============================================================================
# MAIN EXECUTION
# =============================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("PILLAR 2: SPATIAL GRAPHRAG BENCHMARK SUITE")
    print("=" * 70)

    # --- Benchmark 1: Memory Footprint ---
    mem_result = benchmark_memory_footprint(target_nodes=10000, target_edges=25000)

    # Re-initialize for latency tests
    rag = SpatialGraphRAG(seed=42)
    rag.generate_global_map(num_nodes=2000)

    # --- Benchmark 2: Query Latency ---
    query_result = benchmark_query_latency(rag, test_nodes=1000, iterations=200)

    # --- Benchmark 3: Mutation Latency ---
    mut_result = benchmark_mutation_latency(rag, detour_nodes=50, iterations=200)

    # --- Benchmark 4: Token Payload ---
    token_result = benchmark_token_payload(rag, iterations=100)

    # --- Summary ---
    print("\n" + "=" * 70)
    print("BENCHMARK SUMMARY")
    print("=" * 70)

    all_results = [mem_result, query_result, mut_result, token_result]
    all_passed = all(r['passed'] for r in all_results)

    for r in all_results:
        status = "PASS" if r['passed'] else "FAIL"
        print(f"  {r['metric']:<25} {status}")

    print(f"\n  OVERALL: {'ALL TARGETS MET' if all_passed else 'SOME TARGETS MISSED'}")

    # --- CSV Generation ---
    output_dir = "./output/"
    os.makedirs(output_dir, exist_ok=True)
    csv_path = os.path.join(output_dir, "pillar2_spatial_graphrag_benchmarks.csv")

    rows = [
        {
            'Pillar': 'Pillar_2', 'Metric': 'Memory_Footprint', 'Sub_Metric': 'Peak_RAM_MB',
            'Target_Value': 15, 'Actual_Value': mem_result['peak_mb'], 'Unit': 'MB',
            'Status': 'PASS' if mem_result['passed'] else 'FAIL',
            'Notes': f"{mem_result['actual_nodes']} nodes, {mem_result['actual_edges']} edges. Sparse-by-design."
        },
        {
            'Pillar': 'Pillar_2', 'Metric': 'Memory_Footprint', 'Sub_Metric': 'Current_RAM_MB',
            'Target_Value': 15, 'Actual_Value': mem_result['current_mb'], 'Unit': 'MB',
            'Status': 'PASS' if mem_result['passed'] else 'FAIL',
            'Notes': "Current allocation at snapshot time (tracemalloc)."
        },
        {
            'Pillar': 'Pillar_2', 'Metric': 'Query_Latency', 'Sub_Metric': 'Dijkstra_Avg_MS',
            'Target_Value': 2, 'Actual_Value': query_result['dijkstra_avg_ms'], 'Unit': 'ms',
            'Status': 'PASS' if query_result['dijkstra_avg_ms'] < 2 else 'FAIL',
            'Notes': f"Baseline Dijkstra over {query_result['test_nodes']} nodes, {query_result['iterations']} iterations."
        },
        {
            'Pillar': 'Pillar_2', 'Metric': 'Query_Latency', 'Sub_Metric': 'AStar_Avg_MS',
            'Target_Value': 2, 'Actual_Value': query_result['astar_avg_ms'], 'Unit': 'ms',
            'Status': 'PASS' if query_result['astar_avg_ms'] < 2 else 'FAIL',
            'Notes': f"A* with Euclidean heuristic over {query_result['test_nodes']} nodes, {query_result['iterations']} iterations."
        },
        {
            'Pillar': 'Pillar_2', 'Metric': 'Query_Latency', 'Sub_Metric': 'Best_Algorithm_Avg_MS',
            'Target_Value': 2, 'Actual_Value': query_result['best_avg_ms'], 'Unit': 'ms',
            'Status': 'PASS' if query_result['passed'] else 'FAIL',
            'Notes': f"Winner: {query_result['best_algorithm']}."
        },
        {
            'Pillar': 'Pillar_2', 'Metric': 'Mutation_Latency', 'Sub_Metric': 'Edge_Destroy_Plus_Detour_Avg_MS',
            'Target_Value': 5, 'Actual_Value': mut_result['avg_ms'], 'Unit': 'ms',
            'Status': 'PASS' if mut_result['passed'] else 'FAIL',
            'Notes': f"L0 interrupt: edge severed + {mut_result['detour_nodes']}-node detour. {mut_result['iterations']} iterations."
        },
        {
            'Pillar': 'Pillar_2', 'Metric': 'Mutation_Latency', 'Sub_Metric': 'Edge_Destroy_Plus_Detour_Min_MS',
            'Target_Value': 5, 'Actual_Value': mut_result['min_ms'], 'Unit': 'ms',
            'Status': 'PASS' if mut_result['min_ms'] < 5 else 'FAIL',
            'Notes': "Best-case mutation latency."
        },
        {
            'Pillar': 'Pillar_2', 'Metric': 'Token_Payload', 'Sub_Metric': 'Max_Tokens',
            'Target_Value': 50, 'Actual_Value': token_result['max_tokens'], 'Unit': 'tokens',
            'Status': 'PASS' if token_result['passed'] else 'FAIL',
            'Notes': f"Local context summary. Avg={token_result['avg_tokens']}, Min={token_result['min_tokens']}."
        },
        {
            'Pillar': 'Pillar_2', 'Metric': 'Token_Payload', 'Sub_Metric': 'Avg_Tokens',
            'Target_Value': 50, 'Actual_Value': token_result['avg_tokens'], 'Unit': 'tokens',
            'Status': 'PASS' if token_result['avg_tokens'] < 50 else 'FAIL',
            'Notes': f"Sample: '{token_result['sample_payload']}'"
        },
    ]

    fieldnames = ['Pillar', 'Metric', 'Sub_Metric', 'Target_Value', 'Actual_Value', 'Unit', 'Status', 'Notes']

    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nCSV saved to: {csv_path}")
