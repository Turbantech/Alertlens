"""RAG over policy docs: chunk BY SECTION, embed into persistent Chroma, search with citations."""
import os, re, sys
from pathlib import Path
import chromadb
from dotenv import load_dotenv
from langchain_openai import OpenAIEmbeddings

load_dotenv()
K = 3                                   # top-k results (change here for the eval experiment)
POLICY_DIR = Path(__file__).parent / "data" / "policies"
DB_DIR = str(Path(__file__).parent / "chroma_db")
SECTION_RE = re.compile(r"^## Section (\d+\.\d+) - (.+)$", re.M)

def _embedder():
    # Embeddings go straight to OpenAI (the gateway is only for chat)
    return OpenAIEmbeddings(model=os.environ["EMBED_MODEL"])

def _collection():
    client = chromadb.PersistentClient(path=DB_DIR)
    return client.get_or_create_collection("policies")

def chunk_policies():
    """One chunk per '## Section X.Y - Title', with metadata."""
    chunks = []
    for f in sorted(POLICY_DIR.glob("*.md")):
        text = f.read_text(encoding="utf-8")
        matches = list(SECTION_RE.finditer(text))
        for i, m in enumerate(matches):
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            body = text[m.end():end].strip()
            chunks.append({
                "id": f"{f.name}-{m.group(1)}",
                "text": f"{f.name} Section {m.group(1)} - {m.group(2)}\n{body}",
                "meta": {"doc_id": f.name, "section": m.group(1), "title": m.group(2)},
            })
    return chunks

def ingest():
    """Idempotent: upsert by id, so re-running never duplicates."""
    chunks = chunk_policies()
    vecs = _embedder().embed_documents([c["text"] for c in chunks])
    _collection().upsert(ids=[c["id"] for c in chunks], embeddings=vecs,
                         documents=[c["text"] for c in chunks],
                         metadatas=[c["meta"] for c in chunks])
    print(f"Ingested {len(chunks)} chunks")

def search_policy(query: str, k: int = K) -> str:
    """Search AML policy manual. Returns top sections, each tagged like [structuring.md §2.1]."""
    qv = _embedder().embed_query(query)
    res = _collection().query(query_embeddings=[qv], n_results=k)
    out = []
    for doc, meta in zip(res["documents"][0], res["metadatas"][0]):
        out.append(f"[{meta['doc_id']} §{meta['section']}]\n{doc}")
    return "\n\n".join(out)

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "ingest":
        ingest()
    else:  # test: 3 sample queries
        for q in ["many cash deposits just under reporting limit",
                  "money arrives and leaves within 48 hours",
                  "transfers to a sanctioned or high-risk country"]:
            print(f"\n=== {q}")
            for line in search_policy(q).splitlines():
                if line.startswith("["): print(line)