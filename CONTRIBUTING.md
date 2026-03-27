# Contributing

Thanks for your interest in this project! There are two main ways to contribute.

## Adapt for your region

The fastest way to get started is to fork this repo and use the [REBUILD.md](REBUILD.md) prompt with [Claude Code](https://claude.ai/code) to adapt the pipeline for your geography. If you run into issues, open a [Region Adaptation](https://github.com/jtlevine18/weather-ai-pipeline/issues/new?template=region_adaptation.md) issue — your experience helps improve the adaptation guide.

## Contribute back

Bug fixes and improvements to the global pipeline infrastructure are welcome.

### What makes a good PR

- **Bug fixes** — broken API calls, data pipeline failures, test regressions
- **Global improvements** — better fallback handling, new weather data sources, pipeline performance
- **Documentation** — clearer REBUILD.md instructions, new adaptation examples

### What to avoid

- Changes that break the India reference implementation (it's the default and must keep working)
- Region-specific code that only applies to one geography (keep that in your fork)
- Large refactors without discussion — open an issue first

### Code conventions

- Python 3.11+, type hints, async where the pipeline uses async
- Pydantic v2 for data contracts at stage boundaries
- Tests in `tests/` — run with `pytest`
- Keep `stations.json` and `farmers.json` as the geography configuration layer

### Getting started

```bash
git clone https://github.com/jtlevine18/weather-ai-pipeline.git
cd weather-ai-pipeline
pip install -r requirements.txt
cp .env.example .env  # fill in API keys + DATABASE_URL
pytest tests/
```
