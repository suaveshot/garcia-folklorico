"""
Shared retry decorator with exponential backoff.

Usage:
    from shared_utils import with_retry

    @with_retry(max_attempts=3, base_delay=5, exceptions=(IOError,))
    def fetch_data():
        ...
"""

import functools
import logging
import time


def with_retry(max_attempts=3, base_delay=5, exceptions=(Exception,), label=None):
    """Retry with exponential backoff: 5s, 10s, 20s."""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            name = label or func.__qualname__
            last_exc = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exc = e
                    if attempt < max_attempts:
                        delay = base_delay * (2 ** (attempt - 1))
                        logging.warning(
                            f"[retry] {name} attempt {attempt}/{max_attempts} failed: {e}. "
                            f"Retrying in {delay}s..."
                        )
                        time.sleep(delay)
                    else:
                        logging.error(
                            f"[retry] {name} failed after {max_attempts} attempts: {e}"
                        )
            raise last_exc
        return wrapper
    return decorator
