"""Small, non-destructive event photo pipeline."""
from pathlib import Path
import shutil
import os
import math
from enum import Enum
from typing import Annotated

from dotenv import load_dotenv
import imagehash
from rich.console import Console
from rich.progress import track
from rich.table import Table
import typer

from .dedupe import group_duplicates
from .filters import exposure_flag, sharpness
from .loader import SUPPORTED, read_photo
from .providers import GeminiProvider, MockProvider
from .ranker import rank
from .report import write_csv, write_html

app = typer.Typer(no_args_is_help=True, pretty_exceptions_enable=False)
console = Console()


class Provider(str, Enum):
    gemini = 'gemini'
    mock = 'mock'


@app.callback()
def main():
    """Curate event photos without changing originals."""


@app.command()
def run(
    photos: Annotated[Path, typer.Argument(exists=True, file_okay=False, readable=True)],
    out: Annotated[Path, typer.Option(help='New or empty output directory.')] = Path('picks'),
    top: Annotated[int, typer.Option(min=1)] = 15,
    provider: Annotated[Provider, typer.Option()] = Provider.gemini,
    model: Annotated[str, typer.Option()] = 'gemini-2.5-flash',
    batch_size: Annotated[int, typer.Option(min=1, max=16)] = 5,
    cache_dir: Annotated[Path, typer.Option()] = Path('.cache'),
    blur_threshold: Annotated[float, typer.Option(min=0)] = 100,
    dup_distance: Annotated[int, typer.Option(min=0, max=64)] = 6,
    exposure_percent: Annotated[float, typer.Option(min=0, max=100)] = 20,
    caption_style: Annotated[str, typer.Option()] = 'Casual event Instagram, no hashtag spam',
):
    """Filter, rank and copy the best photos; scan the input folder non-recursively."""
    if not math.isfinite(blur_threshold) or not math.isfinite(exposure_percent):
        raise typer.BadParameter('Thresholds must be finite numbers')
    load_dotenv(Path.cwd() / '.env')
    source, destination = photos.resolve(), out.resolve()
    if source == destination or source in destination.parents or destination in source.parents:
        raise typer.BadParameter('--out must be separate from the input tree')
    if destination.exists() and (not destination.is_dir() or any(destination.iterdir())):
        raise typer.BadParameter('--out must be a new or empty directory; existing files are never overwritten')
    key = os.getenv('GEMINI_API_KEY', '').strip()
    if provider == Provider.gemini and (not key or key == 'your-key-here'):
        console.print('WARNING: GEMINI_API_KEY is unset or a placeholder; using mock ranking. No AI visual judgment.', style='yellow')
        provider = Provider.mock
    scorer = GeminiProvider(key, model) if provider == Provider.gemini else MockProvider()
    console.print(f'Provider: {scorer.name} | Model: {scorer.model}', markup=False)
    paths = sorted(p for p in source.iterdir() if p.is_file() and not p.is_symlink() and p.suffix.lower() in SUPPORTED)
    if not paths:
        raise typer.BadParameter('No supported photos found in the input folder')
    records = []
    for path in track(paths, description='Inspecting photos', console=console):
        photo, image = read_photo(path)
        if image is not None:
            photo.sharpness = sharpness(image)
            photo.exposure = exposure_flag(image, exposure_percent)
            photo.phash = imagehash.phash(image)
            if photo.sharpness < blur_threshold:
                photo.reasons.append(f'Blurry: {photo.sharpness:.2f} < {blur_threshold:g}')
            if photo.exposure:
                photo.reasons.append(photo.exposure)
        records.append(photo)
    duplicates = group_duplicates(records, dup_distance)
    try:
        tokens, cache_hits = rank(records, scorer, caption_style, cache_dir, batch_size, console)
    except (RuntimeError, OSError) as exc:
        console.print(str(exc) if isinstance(exc, RuntimeError) else 'Cannot read/write the local cache directory.', style='red', markup=False)
        raise typer.Exit(1) from None
    finally:
        if isinstance(scorer, GeminiProvider):
            scorer.client.close()
    candidates = sorted((p for p in records if p.assessment), key=lambda p: (-p.assessment['score'], -p.sharpness, p.path.name))
    destination.mkdir(parents=True, exist_ok=True)
    for photo in candidates[:top]:
        # Exclusive creation prevents replacing anything, even after preflight.
        with photo.path.open('rb') as src, (destination / photo.path.name).open('xb') as dst:
            shutil.copyfileobj(src, dst)
        photo.picked = True
    for photo in candidates[top:]:
        photo.reasons.append(f'Outside top {top}; ' + photo.assessment['reason'])
    write_csv(records, destination)
    write_html(records, destination, scorer.name, scorer.model)
    table = Table(title='Event Photo Curator')
    table.add_column('Metric')
    table.add_column('Count', justify='right')
    for label, count in [('Scanned', len(records)), ('Blurry', sum(p.sharpness < blur_threshold for p in records if p.preview)),
                         ('Dupes', duplicates), ('Exposure issues', sum(bool(p.exposure) for p in records)),
                         ('Unreadable', sum(not p.preview for p in records)), ('Picked', sum(p.picked for p in records)),
                         ('Cache hits', cache_hits), ('Estimated tokens used', tokens)]:
        table.add_row(label, str(count))
    console.print(table)
    console.print(f'Output: {destination}', markup=False)
