import argparse
import sys
import time
from pathlib import Path


def print_banner():
    print("""
===================================================================
  RouteX Knowledge Base Ingestion Engine (FORGE '26 Buildathon)
  Himalayan Disaster SOPs, IRC Engineering Codes & IMD Matrices
===================================================================
""")


def main():
    parser = argparse.ArgumentParser(
        description="Ingest and verify mountain corridor disaster SOPs in pgvector.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--source",
        type=str,
        default="data/rag_documents",
        help="Path to directory containing SOP manuals (default: data/rag_documents)",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Purge existing pgvector collection before indexing",
    )
    parser.add_argument(
        "--interactive",
        "-i",
        action="store_true",
        help="Launch interactive terminal Q&A copilot after ingestion",
    )

    args = parser.parse_args()
    source_dir = Path(args.source)

    print_banner()

    if not source_dir.exists():
        print(f"[!] Error: Target directory '{source_dir}' does not exist.")
        sys.exit(1)

    # Lazy import to keep CLI startup snappy
    print("[*] Initializing embedding model and database connection...")
    t0 = time.time()

    from backend.services.rag import CorridorIntelligenceService

    service = CorridorIntelligenceService()
    init_time = time.time() - t0
    print(f"    Connected to pgvector collection: '{service.collection_name}' ({init_time:.2f}s)")
    print(f"    Embedding backend: {service.emb_provider} | LLM: {service.llm_provider}\n")

    files = [f for f in source_dir.glob("*") if f.suffix.lower() in (".md", ".pdf", ".txt")]
    print(f"[*] Discovered {len(files)} domain manuals in '{source_dir}':")
    for idx, f in enumerate(files, 1):
        kb_size = f.stat().st_size / 1024
        print(f"    {idx}. {f.name:<36} ({kb_size:.1f} KB)")

    print(f"\n[*] Processing chunks and generating vector embeddings (reset={args.reset})...")
    t1 = time.time()
    total_chunks = service.ingest(str(source_dir), reset_collection=args.reset)
    elapsed = time.time() - t1

    print(f"[✓] Ingestion successful! Stored {total_chunks} chunks in {elapsed:.2f}s.")

    # Smoke test verification
    print("\n[*] Running self-test query: 'evacuation protocol for Class 3 landslide'...")
    test_res = service.ask("What is the evacuation protocol for a Class 3 landslide?", top_k=2)
    print(f"    Retrieval verified: {test_res['chunks_retrieved']} source chunks cited.")
    for s in test_res["sources"]:
        print(f"    - Cited: {s['file']} ({s['page']})")

    if args.interactive:
        print("\n" + "=" * 67)
        print(" Interactive Terminal Copilot (Type 'exit' or 'quit' to return)")
        print("=" * 67)
        while True:
            try:
                user_input = input("\nRouteX-Field > ").strip()
                if not user_input or user_input.lower() in ("exit", "quit", "q"):
                    print("Exiting copilot.")
                    break

                t_query = time.time()
                res = service.ask(user_input, top_k=4)
                q_elapsed = time.time() - t_query

                print(f"\n--- Grounded Response ({q_elapsed:.2f}s) ---")
                print(res["answer"])
                print("\nSources:")
                for src in res["sources"]:
                    print(f"  • {src['file']} [{src['page']}]")

            except (KeyboardInterrupt, EOFError):
                print("\nExiting.")
                break


if __name__ == "__main__":
    main()
