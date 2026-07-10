# sekoia.star -- copy-paste helpers for Starlark playbook scripts.
# load() is disabled in the sandbox, so PASTE the functions you need into your script.
# Pure Starlark; the pad_window helper uses the host parse_time/format_time primitives.

def get(obj, path, default = None):
    """Safe dotted access over an event (works whether the key is flattened
    'a.b.c' or nested {'a':{'b':{'c':...}}}). Returns `default` if absent."""
    if type(obj) != "dict":
        return default
    if path in obj:               # flattened dotted key present directly
        return obj[path]
    cur = obj
    for part in path.split("."):
        if type(cur) != "dict" or part not in cur:
            return default
        cur = cur[part]
    return cur

def _dur(spec):
    """'5m'/'1h'/'2d'/'30s' or a number of seconds -> seconds (int)."""
    if type(spec) == "int" or type(spec) == "float":
        return int(spec)
    units = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    return int(spec[:-1]) * units[spec[-1]]

def pad_window(first, last, pad = "5m"):
    """Return (earliest_iso, latest_iso) padded by `pad` around [first, last].
    Fixes the single-instant window (first == last) case. Needs the host
    parse_time/format_time primitives in scope."""
    p = _dur(pad)
    return (format_time(parse_time(first) - p), format_time(parse_time(last) + p))
