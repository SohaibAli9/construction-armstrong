"""
Animated pipeline dashboard — Rich Live display.

Two context managers, same API:
  LivePipeline   — beautiful animated terminal dashboard
  NoopPipeline   — silent fallback (used with --no-anim or when Rich is missing)

Usage:
    with LivePipeline(total_stages=6, animate=True) as ui:
        ui.start_stage(0, "Page classification")
        ...
        ui.complete_stage(0, elapsed=12.3)
        ...
        ui.set_cost(0.0421)
"""

import time

# ── Emoji / label constants ────────────────────────────────────────

STAGE_EMOJIS = ("🤖", "📐", "🏠", "🧱", "🔍", "🎨")
STAGE_LABELS = (
    "Page classification",
    "Area schedule",
    "Room inventory",
    "Wall geometry",
    "Validation",
    "SVG render",
)

SPINNER = ("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏")

# ── LivePipeline ────────────────────────────────────────────────────


class LivePipeline:
    """Context manager that shows an animated Rich dashboard inside the terminal."""

    def __init__(self, total_stages: int = 6, animate: bool = True):
        self.animate = animate
        self.total = total_stages
        self.statuses = ["waiting"] * total_stages  # waiting | active | done | failed
        self.elapsed = [0.0] * total_stages
        self.fail_msgs = [""] * total_stages
        self.total_cost = 0.0
        self.t_start = 0.0
        self.t_stage = 0.0
        self._tick = 0
        self._live = None
        self._console = None

    # ── public API ──────────────────────────────────────────────────

    def start_stage(self, idx: int, label: str = ""):
        if not self.animate:
            print(f"\n[{idx + 1}/{self.total}] {label or STAGE_LABELS[idx]}")
            return
        self.statuses[idx] = "active"
        self.t_stage = time.time()
        self._push()

    def complete_stage(self, idx: int, elapsed: float):
        if not self.animate:
            print(f"  ✓ done in {elapsed:.1f}s")
            return
        self.statuses[idx] = "done"
        self.elapsed[idx] = elapsed
        self._push()

    def fail_stage(self, idx: int, error: str = ""):
        if not self.animate:
            print(f"  ERROR in stage {idx + 1}")
            return
        self.statuses[idx] = "failed"
        self.fail_msgs[idx] = error
        self._push()

    def set_cost(self, cost: float):
        self.total_cost = cost
        self._push()

    # ── lifecycle ───────────────────────────────────────────────────

    def __rich_console__(self, console, options):
        yield self._build()

    def __enter__(self):
        if not self.animate:
            return self

        # lazy import so the module loads fine without Rich
        from rich.console import Console
        from rich.live import Live

        self._console = Console(force_terminal=True)
        self.t_start = time.time()
        self._live = Live(self, console=self._console, refresh_per_second=10)
        self._live.__enter__()
        return self

    def __exit__(self, *args):
        if self._live:
            self._live.__exit__(*args)

    # ── internals ───────────────────────────────────────────────────

    def _push(self):
        if self._live:
            self._live.update(self._build())

    def _build(self):
        """Construct the full renderable (called every refresh cycle)."""
        from rich.panel import Panel
        from rich.table import Table
        from rich.text import Text
        from rich.style import Style

        self._tick += 1
        tick_char = SPINNER[self._tick % len(SPINNER)]

        table = Table.grid(padding=(0, 1))
        table.add_column(no_wrap=True)

        for i in range(self.total):
            emoji = STAGE_EMOJIS[i]
            label = STAGE_LABELS[i]
            status = self.statuses[i]

            if status == "waiting":
                row = Text(f"  {emoji}  {label}")
                row.stylize(Style(dim=True))
                table.add_row(row)

            elif status == "active":
                live_elapsed = time.time() - self.t_stage
                row = Text.assemble(
                    ("  ", ""),
                    (tick_char, "cyan"),
                    (f"  {emoji}  {label}", "cyan bold"),
                    (f"  {live_elapsed:5.1f}s", "cyan"),
                    ("  Running...", "cyan"),
                )
                table.add_row(row)

            elif status == "done":
                row = Text.assemble(
                    ("  ✓  ", "green bold"),
                    (f"{emoji}  {label}", "green bold"),
                    (f"  {self.elapsed[i]:5.1f}s", "green"),
                )
                table.add_row(row)

            else:  # failed
                row = Text.assemble(
                    ("  ✗  ", "red bold"),
                    (f"{emoji}  {label}", "red bold"),
                    (f"  {self.fail_msgs[i]}", "red"),
                )
                table.add_row(row)

        # ── footer ──────────────────────────────────────────────────
        total_elapsed = time.time() - self.t_start
        footer = Text.assemble(
            (f"  Total: {total_elapsed:5.1f}s", "white bold"),
            "    ",
            (f"Cost: ${self.total_cost:.4f}", "yellow" if self.total_cost else "dim"),
        )
        table.add_row("")
        table.add_row(footer)

        return Panel(
            table,
            title="[bold cyan]ProCalc AI Pipeline[/]",
            subtitle="[dim]ctrl+c to stop[/]",
            border_style="cyan",
            padding=(1, 2),
        )


# ── NoopPipeline (fallback for --no-anim or missing Rich) ──────────


class NoopPipeline:
    """Silent drop-in replacement. All methods are no-ops."""

    def __init__(self, **kwargs):
        pass

    def start_stage(self, idx: int, label: str = ""):
        print(f"\n[{idx + 1}/6] {label}")

    def complete_stage(self, idx: int, elapsed: float):
        print(f"  ✓ done in {elapsed:.1f}s")

    def fail_stage(self, idx: int, error: str = ""):
        print(f"  ERROR in stage {idx + 1}: {error}")

    def set_cost(self, cost: float):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass
