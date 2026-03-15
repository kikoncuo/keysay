"""Model cache management utilities."""

import logging

logger = logging.getLogger(__name__)


def is_model_cached(model_id: str) -> bool:
    """Check if a HuggingFace model is already downloaded."""
    try:
        from huggingface_hub import scan_cache_dir
        cache = scan_cache_dir()
        for repo in cache.repos:
            if repo.repo_id == model_id:
                return True
        return False
    except Exception:
        return True  # Assume cached on error


def list_cached_models() -> list[dict]:
    """List all cached HuggingFace models with sizes.

    Returns list of dicts: {repo_id, size_gb, last_modified}.
    """
    try:
        from huggingface_hub import scan_cache_dir
        cache = scan_cache_dir()
        models = []
        for repo in cache.repos:
            size_gb = repo.size_on_disk / (1024 ** 3)
            last_modified = ""
            for rev in repo.revisions:
                try:
                    lm_val = getattr(rev, "last_modified", None)
                    if lm_val is None:
                        continue
                    lm = lm_val.isoformat() if hasattr(lm_val, "isoformat") else str(lm_val)
                except Exception:
                    lm = ""
                if lm > last_modified:
                    last_modified = lm
            models.append({
                "repo_id": repo.repo_id,
                "size_gb": round(size_gb, 2),
                "last_modified": last_modified,
            })
        return sorted(models, key=lambda m: m["size_gb"], reverse=True)
    except Exception as e:
        logger.error("Failed to scan model cache: %s", e)
        return []


def delete_cached_model(repo_id: str) -> bool:
    """Delete a cached model. Returns True on success."""
    try:
        from huggingface_hub import scan_cache_dir
        cache = scan_cache_dir()
        commit_hashes = []
        for repo in cache.repos:
            if repo.repo_id == repo_id:
                for rev in repo.revisions:
                    commit_hashes.append(rev.commit_hash)
        if not commit_hashes:
            return False
        delete_strategy = cache.delete_revisions(*commit_hashes)
        delete_strategy.execute()
        return True
    except Exception as e:
        logger.error("Failed to delete model %s: %s", repo_id, e)
        return False


def get_cache_size_gb() -> float:
    """Get total size of HuggingFace model cache in GB."""
    try:
        from huggingface_hub import scan_cache_dir
        cache = scan_cache_dir()
        return sum(repo.size_on_disk for repo in cache.repos) / (1024 ** 3)
    except Exception:
        return 0.0
