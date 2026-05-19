from job_terminal_tui import TuiFormatter


def test_formatter_renders_icons_and_indentation() -> None:
    formatter = TuiFormatter()

    formatter.info("Scraping group 'kyc'")
    formatter.success("Found 100 jobs", indent=2)
    formatter.added("Risk Analyst", indent=2)
    formatter.dropped("92 jobs skipped", indent=2)

    assert formatter.render() == "\n".join(
        [
            "• Scraping group 'kyc'",
            "  [green]✓[/green] Found 100 jobs",
            "  [green]+[/green] Risk Analyst",
            "  [red]-[/red] 92 jobs skipped",
        ]
    )


def test_formatter_renders_rejection_reason_on_next_line() -> None:
    formatter = TuiFormatter()

    formatter.rejected_with_reason(
        "Governance, Risk & Compliance Lead",
        'Title includes "Lead".',
        indent=2,
    )

    assert formatter.render() == "\n".join(
        [
            "  [red]✗[/red] Governance, Risk &amp; Compliance Lead",
            '    [dim]Reason: Title includes "Lead".[/dim]',
        ]
    )


def test_formatter_dim_escapes_metadata() -> None:
    assert TuiFormatter.dim("linkedin/li-[123]") == "[dim]linkedin/li-\\[123][/dim]"


def test_formatter_header_preserves_leading_blank_line() -> None:
    formatter = TuiFormatter()

    formatter.header("Zhijun Lin")

    assert formatter.render() == "\nZhijun Lin"
