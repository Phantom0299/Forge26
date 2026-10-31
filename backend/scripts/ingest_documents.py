import argparse
import logging
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("routex.cli")


def main():
    parser = argparse.ArgumentParser(
        description="CLI tool to ingest mountain road SOPs into RouteX pgvector store."
    )
    parser.add_argument(
        "--source",
        type=str,
        default="data/rag_documents",
        help="Path to folder or file containing PDFs/MD manuals",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Clear existing collection before ingesting",
    )
    parser.add_argument(
        "--verify",
        type=str,
        default="landslide road clearance protocol",
        help="Test query to verify retrieval after ingestion",
    )

    args = parser.parse_args()
    source_path = Path(args.source)

    if not source_path.exists():
        logger.error(f"Cannot find source directory: {source_path}")
        sys.exit(1)

    from backend.services.rag import CorridorIntelligenceService

    service = CorridorIntelligenceService()
    logger.info(f"Ingesting documents from {source_path} (reset={args.reset})...")

    total_chunks = service.ingest(str(source_path), reset_collection=args.reset)
    logger.info(f"Done! {total_chunks} chunks stored in pgvector.")

    if args.verify and total_chunks > 0:
        logger.info(f"Running verification query: '{args.verify}'")
        res = service.ask(args.verify, top_k=2)
        logger.info(f"Verification Answer:\n{res['answer'][:300]}...\n")
        logger.info(f"Sources cited: {[s['file'] for s in res['sources']]}")


if __name__ == "__main__":
    main()
