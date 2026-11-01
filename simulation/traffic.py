"""Send steady checkout traffic to the dummy checkout-api.

Requests go out on a fixed schedule (open loop), the way real users arrive, so a slow server
builds a queue instead of slowing the sender down. 40 requests/second at ~200ms each needs
about 8 connections at once.

    python simulation/traffic.py               # 40 req/s until Ctrl+C
    python simulation/traffic.py --rate 20 --url http://localhost:8080
"""

import argparse
import threading
import time
import urllib.error
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

counts: Counter[str] = Counter()
lock = threading.Lock()


def send(url: str) -> None:
    request = urllib.request.Request(f"{url}/checkout", method="POST")
    try:
        with urllib.request.urlopen(request, timeout=35) as response:
            outcome = str(response.status)
    except urllib.error.HTTPError as exc:
        outcome = str(exc.code)
    except OSError:
        outcome = "conn_error"
    with lock:
        counts[outcome] += 1


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--url", default="http://localhost:8080")
    parser.add_argument("--rate", type=float, default=40, help="requests per second")
    args = parser.parse_args()

    interval = 1 / args.rate
    next_send = time.monotonic()
    last_report = next_send
    with ThreadPoolExecutor(max_workers=200) as pool:
        try:
            while True:
                pool.submit(send, args.url)
                next_send += interval
                now = time.monotonic()
                if now - last_report >= 5:
                    with lock:
                        print(time.strftime("%H:%M:%S"), dict(sorted(counts.items())), flush=True)
                        counts.clear()
                    last_report = now
                time.sleep(max(0, next_send - now))
        except KeyboardInterrupt:
            print("stopping")
            pool.shutdown(wait=False, cancel_futures=True)


if __name__ == "__main__":
    main()
