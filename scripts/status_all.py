import json
import urllib.request

CONFIG_PATH = "config/services.json"

def check_http(service_name, cfg):
    url = f"http://{cfg['host']}:{cfg['port']}{cfg.get('endpoint','/')}"
    try:
        with urllib.request.urlopen(url, timeout=2) as r:
            return f"[OK] {service_name} {url} ({r.status})"
    except Exception as e:
        return f"[FAIL] {service_name} {url} ({str(e)})"

def main():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        config = json.load(f)

    print("=== SERVICE STATUS ===")
    for name, cfg in config.items():
        if cfg.get("type") == "http":
            print(check_http(name, cfg))
        else:
            print(f"[SKIP] {name} unknown type")

if __name__ == "__main__":
    main()
