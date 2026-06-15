from __future__ import annotations

from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from cost_model import EstimateResult, ScenarioCosts
from pricing.schema import PricingConfig, format_money
from projection import ProjectedTraffic, compound_annual_factor, yearly_forecast_totals
from report import format_bytes


def format_money_detailed(usd: float, rate: float, show_eur: bool = True) -> str:
    if abs(usd) < 0.01:
        if show_eur:
            return f"${usd:,.4f} (€{usd * rate:,.4f})"
        return f"${usd:,.4f}"
    return format_money(usd, rate, show_eur)


def _print_scenario_table(
    console: Console,
    scenario: ScenarioCosts,
    pricing: PricingConfig,
    period: str,
    *,
    show_calculations: bool = False,
    growth_rate: float = 0.0,
) -> None:
    lines = scenario.monthly if period == "monthly" else scenario.annual
    total = scenario.monthly_total if period == "monthly" else scenario.annual_total
    rate = pricing.display.usd_eur_rate
    show_eur = pricing.display.show_eur

    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Component", style="bold cyan")
    table.add_column("Cost", justify="right")

    for line in lines:
        table.add_row(
            line.label,
            format_money_detailed(line.usd, rate, show_eur),
        )
    table.add_row("", "")
    table.add_row(
        "[bold]Total[/bold]",
        f"[bold]{format_money_detailed(total, rate, show_eur)}[/bold]",
    )

    console.print(
        Panel(
            table,
            title=f"[bold]{scenario.name} — {period}[/bold]",
            border_style="blue",
        )
    )

    if show_calculations:
        print_scenario_calculations(
            console,
            scenario,
            period=period,
            growth_rate=growth_rate,
        )


def scenario_calculation_lines(
    scenario: ScenarioCosts,
    *,
    period: str,
    growth_rate: float = 0.0,
) -> tuple[str, ...]:
    lines = scenario.monthly if period == "monthly" else scenario.annual
    out: list[str] = []
    for line in lines:
        out.append(f"{line.label}:")
        if line.calculation:
            out.extend(f"  {step}" for step in line.calculation)
        else:
            out.append(f"  {line.usd:.2f} USD")
    out.append(
        scenario.total_calculation(period=period, growth_rate=growth_rate),
    )
    if period == "annual" and growth_rate > 0:
        factor = compound_annual_factor(growth_rate)
        out.append(
            f"Annual factor = {factor:.4f} "
            f"(sum of monthly growth over 12 months at {growth_rate:.0%}/yr)"
        )
    return tuple(out)


def print_scenario_calculations(
    console: Console,
    scenario: ScenarioCosts,
    *,
    period: str,
    growth_rate: float = 0.0,
) -> None:
    console.print(
        f"[bold cyan]Show calculations[/bold cyan] — {scenario.name} ({period})"
    )
    for item in scenario_calculation_lines(
        scenario,
        period=period,
        growth_rate=growth_rate,
    ):
        console.print(f"  [dim]{item}[/dim]")
    console.print()


def print_storage_class_comparison(
    console: Console,
    *,
    pricing: PricingConfig,
    comparisons: tuple[ScenarioCosts, ...],
    selected_storage_class: str,
    show_calculations: bool = False,
) -> None:
    rate = pricing.display.usd_eur_rate
    show_eur = pricing.display.show_eur
    sorted_comparisons = sorted(comparisons, key=lambda item: item.monthly_total)
    cheapest = sorted_comparisons[0].monthly_total

    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Storage class")
    table.add_column("Monthly", justify="right")
    table.add_column("Annual", justify="right")
    table.add_column("Δ vs cheapest/mo", justify="right")

    for scenario in sorted_comparisons:
        delta = scenario.monthly_total - cheapest
        delta_text = "—" if delta == 0 else format_money_detailed(delta, rate, show_eur)
        class_label = scenario.name
        if scenario.name == selected_storage_class:
            class_label = f"[bold]{scenario.name}[/bold] (selected)"
        table.add_row(
            class_label,
            format_money_detailed(scenario.monthly_total, rate, show_eur),
            format_money_detailed(scenario.annual_total, rate, show_eur),
            delta_text,
        )

    console.print(
        Panel(
            table,
            title="[bold]Storage class comparison (S3 direct, realistic)[/bold]",
            subtitle=(
                "GET and egress costs are identical across classes; "
                "only storage and Intelligent-Tiering monitoring differ."
            ),
            border_style="magenta",
        )
    )

    if show_calculations:
        console.print(
            "[bold cyan]Show calculations[/bold cyan] — storage class comparison "
            "(storage and monitoring only; GET/egress identical across classes)"
        )
        for scenario in sorted_comparisons:
            storage_lines = tuple(
                line
                for line in scenario.monthly
                if line.label in {"Storage", "Intelligent-Tiering monitoring"}
            )
            if not storage_lines:
                continue
            console.print(f"  [bold]{scenario.name}[/bold]")
            for line in storage_lines:
                for step in line.calculation:
                    console.print(f"    [dim]{step}[/dim]")
        console.print()


def print_yearly_forecast(
    console: Console,
    *,
    pricing: PricingConfig,
    base_annual_total: float,
    growth_rate: float,
    forecast_years: int,
) -> None:
    forecast = yearly_forecast_totals(base_annual_total, growth_rate, forecast_years)
    if not forecast:
        return

    rate = pricing.display.usd_eur_rate
    show_eur = pricing.display.show_eur
    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Year")
    table.add_column("Annual total (S3 direct)", justify="right")

    for year, total in forecast:
        table.add_row(str(year), format_money_detailed(total, rate, show_eur))

    console.print(
        Panel(
            table,
            title="[bold]Multi-year forecast (realistic S3 direct)[/bold]",
            subtitle=(
                f"Year 1 uses growth-adjusted annual totals ({growth_rate:.0%}/yr); "
                "later years compound on year 1."
            ),
            border_style="cyan",
        )
    )


def print_estimate_report(
    console: Console,
    *,
    log_file: Path,
    pricing: PricingConfig,
    traffic: ProjectedTraffic,
    result: EstimateResult,
    pricing_warnings: list[str],
    selected_storage_class: str = "STANDARD",
    growth_rate: float = 0.0,
    forecast_years: int = 0,
    show_calculations: bool = False,
) -> None:
    disclaimer = Table(show_header=False, box=None, padding=(0, 2))
    disclaimer.add_column(style="yellow")
    disclaimer.add_row(
        f"Observed period: {traffic.observed_days:.1f} days "
        f"(scaled ×{traffic.scale_factor:.2f} → "
        f"{traffic.target_month_days:.0f}-day month, {traffic.mode} mode)."
    )
    disclaimer.add_row(
        f"Region: {pricing.region} | Pricing date: {pricing.effective_date}"
    )
    disclaimer.add_row(
        f"FX: 1 USD = {pricing.display.usd_eur_rate:.4f} EUR (indicative only)."
    )
    disclaimer.add_row(f"Detailed estimate storage class: {selected_storage_class}")
    if growth_rate > 0:
        disclaimer.add_row(
            f"Annual totals assume {growth_rate:.0%}/yr growth on all cost lines; "
            "monthly figures are the current run rate."
        )
    disclaimer.add_row("AWS prices change. This is not a billing guarantee.")

    console.print(
        Panel(
            disclaimer,
            title="[bold]Estimate disclaimer[/bold]",
            border_style="yellow",
        )
    )

    traffic_table = Table(show_header=False, box=None, padding=(0, 2))
    traffic_table.add_column("Field", style="bold cyan")
    traffic_table.add_column("Value")
    traffic_table.add_row("Log file", str(log_file))
    traffic_table.add_row(
        "Projected monthly requests",
        f"{traffic.monthly_requests:,.0f}",
    )
    traffic_table.add_row(
        "Projected monthly transfer",
        format_bytes(int(traffic.monthly_bytes)),
    )
    traffic_table.add_row(
        "Conservative traffic buffer",
        f"+{traffic.safety_margin:.0%} on worst-case scenario only",
    )
    console.print(
        Panel(
            traffic_table,
            title="[bold]Projected traffic (realistic)[/bold]",
            border_style="green",
        )
    )

    _print_scenario_table(
        console,
        result.realistic_s3,
        pricing,
        "monthly",
        show_calculations=show_calculations,
        growth_rate=growth_rate,
    )
    _print_scenario_table(
        console,
        result.realistic_s3,
        pricing,
        "annual",
        show_calculations=show_calculations,
        growth_rate=growth_rate,
    )
    if result.realistic_cloudfront is not None:
        _print_scenario_table(
            console,
            result.realistic_cloudfront,
            pricing,
            "monthly",
            show_calculations=show_calculations,
            growth_rate=growth_rate,
        )
        _print_scenario_table(
            console,
            result.realistic_cloudfront,
            pricing,
            "annual",
            show_calculations=show_calculations,
            growth_rate=growth_rate,
        )

    _print_scenario_table(
        console,
        result.conservative,
        pricing,
        "monthly",
        show_calculations=show_calculations,
        growth_rate=growth_rate,
    )
    _print_scenario_table(
        console,
        result.conservative,
        pricing,
        "annual",
        show_calculations=show_calculations,
        growth_rate=growth_rate,
    )

    rate = pricing.display.usd_eur_rate
    savings = result.realistic_s3.monthly_total - (
        result.realistic_cloudfront.monthly_total
        if result.realistic_cloudfront
        else result.realistic_s3.monthly_total
    )
    if result.realistic_cloudfront and savings > 0:
        console.print(
            "[green]Recommendation:[/green] CloudFront saves "
            f"{format_money_detailed(savings, rate)} per month versus S3 direct."
        )

    print_yearly_forecast(
        console,
        pricing=pricing,
        base_annual_total=result.realistic_s3.annual_total,
        growth_rate=growth_rate,
        forecast_years=forecast_years,
    )

    for warning in pricing_warnings:
        console.print(f"[yellow]Warning:[/yellow] {warning}")
