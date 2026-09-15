"""
report_generator.py — gera report.md + report.html + stats JSON a partir de estado de simulação
Gráficos ASCII + tabelas (sem libs externas). Entrada: dict de estado ou arquivos demo.
"""
from __future__ import annotations

import html
import json
import math
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# --- stats ---
def compute_stats(values: List[float]) -> Dict[str, float]:
    if not values:
        return {"count": 0, "mean": 0, "median": 0, "std": 0, "min": 0, "max": 0}
    return {
        "count": len(values),
        "mean": round(statistics.mean(values), 6),
        "median": round(statistics.median(values), 6),
        "std": round(statistics.pstdev(values), 6) if len(values) > 1 else 0.0,
        "min": round(min(values), 6),
        "max": round(max(values), 6),
        "p95": round(sorted(values)[int(len(values)*0.95)] ,6) if len(values) > 1 else round(values[0],6),
    }

def ascii_histogram(values: List[float], width: int = 40, bins: int = 12) -> str:
    if not values:
        return "(sem dados)"
    lo, hi = min(values), max(values)
    if lo == hi:
        return f"[{lo}] " + "█"*width + f" ({len(values)} valores)"
    step = (hi - lo) / bins
    counts = [0]*bins
    for v in values:
        idx = min(int((v - lo)/step), bins-1)
        counts[idx] += 1
    mx = max(counts) or 1
    lines = []
    for i, c in enumerate(counts):
        b0 = lo + i*step
        b1 = b0 + step
        bar = "█" * int(c / mx * width)
        lines.append(f"{b0:8.2f}–{b1:8.2f} | {bar:<{width}} {c}")
    return "\n".join(lines)

def ascii_line(values: List[float], height: int = 8, width: int = 60) -> str:
    if not values:
        return "(sem dados)"
    # downsample para width
    n = len(values)
    if n > width:
        step = n / width
        sampled = [values[int(i*step)] for i in range(width)]
    else:
        sampled = values
    lo, hi = min(sampled), max(sampled)
    if lo == hi:
        return "─"*len(sampled) + f"  (const {lo})"
    rows = []
    for r in range(height, -1, -1):
        thresh = lo + (hi-lo)*r/height
        line = "".join("●" if v >= thresh else " " for v in sampled)
        label = f"{thresh:7.2f} │" if r % 2 == 0 else "        │"
        rows.append(label + line)
    rows.append("        └" + "─"*len(sampled))
    return "\n".join(rows)

# --- report ---
def generate_report(
    state: Dict[str, Any],
    out_dir: str | Path = "reports",
    name: str = "report",
) -> Dict[str, Path]:
    """
    state exemplo:
      {
        "simulation": {"id": 1, "type": "sir", "name": "Demo SIR"},
        "params": {"beta": 0.3, "gamma": 0.1},
        "series": {"infected": [10,12,...], "recovered": [...]},
        "metrics": {"mae": 1.2},
        "notes": "texto livre"
      }
    Gera: report.md, report.html, stats.json
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    sim = state.get("simulation", {})
    params = state.get("params", {})
    series: Dict[str, List[float]] = state.get("series", {})
    metrics = state.get("metrics", {})

    stats: Dict[str, Dict[str, float]] = {k: compute_stats(v) for k, v in series.items()}

    # --- stats.json ---
    stats_path = out_dir / f"{name}_stats.json"
    with open(stats_path, "w", encoding="utf-8") as f:
        json.dump({"simulation": sim, "params": params, "metrics": metrics, "stats": stats, "generated_at": datetime.now(timezone.utc).isoformat()}, f, indent=2, ensure_ascii=False)

    # --- report.md ---
    md_lines: List[str] = []
    md_lines.append(f"# Relatório — {sim.get('name','Simulação')} (`{sim.get('type','generic')}`)")
    md_lines.append(f"\n_Gerado em {datetime.now(timezone.utc).isoformat()} | id={sim.get('id','-')}_\n")
    if params:
        md_lines.append("## Parâmetros\n")
        md_lines.append("| parâmetro | valor |")
        md_lines.append("|---|---|")
        for k, v in params.items():
            md_lines.append(f"| `{k}` | `{v}` |")
        md_lines.append("")
    if metrics:
        md_lines.append("## Métricas\n")
        md_lines.append("| métrica | valor |")
        md_lines.append("|---|---|")
        for k, v in metrics.items():
            md_lines.append(f"| {k} | {v} |")
        md_lines.append("")
    # tabelas stats
    if stats:
        md_lines.append("## Estatísticas por série\n")
        # header
        md_lines.append("| série | count | mean | median | std | min | max | p95 |")
        md_lines.append("|---|---|---|---|---|---|---|---|---|")
        for k, s in stats.items():
            md_lines.append(f"| {k} | {s['count']} | {s['mean']} | {s['median']} | {s['std']} | {s['min']} | {s['max']} | {s['p95']} |")
        md_lines.append("")
        # gráficos
        for k, vals in series.items():
            md_lines.append(f"### {k}\n")
            md_lines.append("**Histograma**\n```")
            md_lines.append(ascii_histogram(vals))
            md_lines.append("```\n")
            md_lines.append("**Série temporal (amostrada)**\n```")
            md_lines.append(ascii_line(vals))
            md_lines.append("```\n")
    if state.get("notes"):
        md_lines.append(f"## Notas\n{state['notes']}\n")
    md_lines.append("---\n*Gerado por pipeline/report_generator.py*")
    md_path = out_dir / f"{name}.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))

    # --- report.html ---
    # converte md simples para html (sem libs)
    html_body = f"<h1>Relatório — {html.escape(str(sim.get('name','Simulação')))} <code>{html.escape(str(sim.get('type','generic')))}</code></h1>"
    html_body += f"<p><em>Gerado em {html.escape(datetime.now(timezone.utc).isoformat())} | id={html.escape(str(sim.get('id','-')))}</em></p>"
    if params:
        html_body += "<h2>Parâmetros</h2><table border='1' cellpadding='6' cellspacing='0'><tr><th>parâmetro</th><th>valor</th></tr>"
        for k, v in params.items():
            html_body += f"<tr><td><code>{html.escape(str(k))}</code></td><td><code>{html.escape(str(v))}</code></td></tr>"
        html_body += "</table>"
    if metrics:
        html_body += "<h2>Métricas</h2><table border='1' cellpadding='6'><tr><th>métrica</th><th>valor</th></tr>"
        for k, v in metrics.items():
            html_body += f"<tr><td>{html.escape(str(k))}</td><td>{html.escape(str(v))}</td></tr>"
        html_body += "</table>"
    if stats:
        html_body += "<h2>Estatísticas por série</h2><table border='1' cellpadding='6'><tr><th>série</th><th>count</th><th>mean</th><th>median</th><th>std</th><th>min</th><th>max</th><th>p95</th></tr>"
        for k, s in stats.items():
            html_body += f"<tr><td>{html.escape(k)}</td><td>{s['count']}</td><td>{s['mean']}</td><td>{s['median']}</td><td>{s['std']}</td><td>{s['min']}</td><td>{s['max']}</td><td>{s['p95']}</td></tr>"
        html_body += "</table>"
        for k, vals in series.items():
            html_body += f"<h3>{html.escape(k)}</h3>"
            html_body += "<h4>Histograma</h4><pre>" + html.escape(ascii_histogram(vals)) + "</pre>"
            html_body += "<h4>Série temporal</h4><pre>" + html.escape(ascii_line(vals)) + "</pre>"
    if state.get("notes"):
        html_body += f"<h2>Notas</h2><p>{html.escape(str(state['notes']))}</p>"
    html_doc = f"""<!doctype html><html lang="pt"><head><meta charset="utf-8"><title>Relatório {html.escape(str(sim.get('name','')))}</title>
    <style>body{{font-family: ui-sans,system-ui, -apple-system, Segoe UI, Roboto, sans-serif; max-width: 900px; margin: 2rem auto; padding: 0 1rem;}} pre{{background:#f6f8fa; padding:12px; overflow:auto;}} table{{border-collapse:collapse;}} th{{background:#eee;}}</style>
    </head><body>{html_body}<hr><small>Gerado por pipeline/report_generator.py</small></body></html>"""
    html_path = out_dir / f"{name}.html"
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_doc)

    return {"md": md_path, "html": html_path, "stats": stats_path}


if __name__ == "__main__":
    import math, random
    demo = {
        "simulation": {"id": 1, "type": "sir", "name": "Demo SIR 200"},
        "params": {"beta": 0.3, "gamma": 0.1, "N": 1000},
        "series": {
            "infected": [10 + 5*math.sin(i/10) + random.gauss(0,1) for i in range(120)],
            "recovered": [i*2 for i in range(120)],
        },
        "metrics": {"mae": 1.82, "r2": 0.94},
        "notes": "Dados sintéticos para validação do gerador.",
    }
    out = generate_report(demo, out_dir="/tmp/reports_demo", name="report")
    print(out)
    print("report OK")
