from orchestrator.litellm import PriceInfo, cache_price_info, load_cached_price_info


def test_price_cache_roundtrip() -> None:
    info = PriceInfo(
        model="qwen/qwen3.6-plus",
        input_per_million_usd=0.325,
        output_per_million_usd=1.95,
    )
    cache_price_info(info)
    cached = load_cached_price_info()

    assert cached is not None
    assert cached.model == "qwen/qwen3.6-plus"
    assert cached.input_per_million_usd == 0.325
    assert cached.output_per_million_usd == 1.95
