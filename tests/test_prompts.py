import prompts


def test_all_15_personas_defined():
    expected = {
        "researcher",
        "bull_fundamentals", "bull_growth", "bull_macro",
        "bull_moat", "bull_capital", "bull_technicals",
        "bear_risk", "bear_valuation", "bear_headwinds",
        "bear_disruption", "bear_accounting", "bear_technicals",
        "judge", "price_target",
    }
    assert set(prompts.SYSTEM_PROMPTS.keys()) == expected


def test_each_persona_is_nonempty_string():
    for name, text in prompts.SYSTEM_PROMPTS.items():
        assert isinstance(text, str), f"{name} not a string"
        assert len(text.strip()) > 50, f"{name} suspiciously short"


def test_schemas_are_valid_json_schema_dicts():
    for name in ("JUDGE_SCHEMA", "PRICE_TARGET_SCHEMA"):
        schema = getattr(prompts, name)
        assert isinstance(schema, dict)
        assert schema.get("type") == "object"
        assert "properties" in schema
        assert "required" in schema


def test_judge_schema_shape():
    s = prompts.JUDGE_SCHEMA
    props = s["properties"]
    assert set(s["required"]) >= {"clashPoints", "winner", "verdict", "summary"}
    assert props["winner"]["enum"] == ["BULL", "BEAR"]
    assert props["verdict"]["type"] == "integer"


def test_price_target_schema_shape():
    s = prompts.PRICE_TARGET_SCHEMA
    props = s["properties"]
    assert set(s["required"]) >= {
        "currentPrice", "bullCase", "baseCase", "bearCase",
        "expectedValue", "timeHorizon", "methodology",
    }
    for case in ("bullCase", "baseCase", "bearCase"):
        case_props = props[case]["properties"]
        assert set(case_props.keys()) >= {"price", "probability", "reasoning"}
