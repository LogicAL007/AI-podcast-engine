# Backlog

The problems found in the review of 31 October 2026, with their severity, priority, risk,
recommendation and "resolved when" criteria, are in the defect and risk report:

- [PE-DRR-001 Defect and Risk Report (PDF)](reports/PE-DRR-001_defect-and-risk-report.pdf)
- Its source and register: [reports/defect_risk_report.py](reports/defect_risk_report.py)

To update it, edit the item in `ITEMS` (status, notes), bump `VERSION`, add a line to
`REVISIONS`, and render again:

```sh
pip install -e ".[reports]"
make -C research report   # research/ is git-ignored, local only
```
