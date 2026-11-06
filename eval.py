"""Compare tool output with hand-picked promos.

labels.csv columns: episode,start,end,note   (times as MM:SS.ss)
A hand label counts as found if any tool promo overlaps it by IoU >= 0.5.

python eval.py --labels labels.csv --pred outputs/run/promos_ranked.json
"""
import argparse
import csv
import json


def sec(t: str) -> float:
    m, s = t.strip().split(":")
    return int(m) * 60 + float(s)


def iou(a, b):
    inter = max(0.0, min(a[1], b[1]) - max(a[0], b[0]))
    union = (a[1] - a[0]) + (b[1] - b[0]) - inter
    return inter / union if union else 0.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--labels", required=True)
    ap.add_argument("--pred", required=True)
    ap.add_argument("--iou", type=float, default=0.5)
    args = ap.parse_args()

    labels = [r for r in csv.DictReader(open(args.labels)) if r["episode"].strip() and not r["episode"].startswith("#")]
    preds = json.load(open(args.pred))
    pred_spans = [(i, s["episode"], s["start"], s["end"]) for i, p in enumerate(preds) for s in p["segments"]]

    found = 0
    for lab in labels:
        ep, span = int(lab["episode"]), (sec(lab["start"]), sec(lab["end"]))
        best = max([(iou(span, (s, e)), i) for i, pe, s, e in pred_spans if pe == ep], default=(0, None))
        hit = best[0] >= args.iou
        found += hit
        print(f"Ep{ep} {lab['start']}-{lab['end']}  best IoU {best[0]:.2f}  "
              f"{'FOUND (rank ' + str(best[1] + 1) + ')' if hit else 'MISSED'}  {lab.get('note', '')}")
    print(f"\nRecall: {found}/{len(labels)} hand-picked promos found in the tool's list")


if __name__ == "__main__":
    main()
