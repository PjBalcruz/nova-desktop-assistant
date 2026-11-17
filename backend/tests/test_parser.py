from app.parser import parse_command

PROFILES = {"chrome", "default", "ag", "mp", "work"}


def test_open_app_with_wake_word():
    cmd = parse_command("Nova, open Discord.", PROFILES)
    assert (cmd.kind, cmd.target, cmd.profile) == ("open", "Discord", None)


def test_open_site_with_profile():
    cmd = parse_command("open github on my AG account", PROFILES)
    assert cmd.target == "github" and cmd.profile == "ag"


def test_unknown_suffix_stays_in_target():
    cmd = parse_command("open facebook on mars", PROFILES)
    assert cmd.target == "facebook on mars" and cmd.profile is None


def test_search_with_engine():
    cmd = parse_command("search youtube for programming tutorials", PROFILES)
    assert (cmd.kind, cmd.engine, cmd.target) == ("search", "youtube", "programming tutorials")


def test_open_and_search():
    cmd = parse_command("Open YouTube and search for lofi music", PROFILES)
    assert (cmd.kind, cmd.engine, cmd.target) == ("search", "youtube", "lofi music")


def test_search_defaults_to_google():
    cmd = parse_command("search react tutorials", PROFILES)
    assert (cmd.engine, cmd.target) == ("google", "react tutorials")


def test_unrelated_sentence_is_not_understood():
    assert parse_command("what is the weather", PROFILES) is None