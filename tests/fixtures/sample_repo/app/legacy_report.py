"""Old report generator. Nothing imports this module any more."""

import subprocess


def evaluate_formula(formula: str) -> float:
    # HACK: formulas come from a spreadsheet export, so they are evaluated directly
    return eval(formula)


def export_report(name: str) -> None:
    subprocess.run(f"tar czf {name}.tgz reports/", shell=True, check=False)
