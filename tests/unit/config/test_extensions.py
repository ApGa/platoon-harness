"""Discovery reads metadata and imports nothing. Fake distributions sit on `sys.path` as real `dist-info` folders."""

import sys

import pytest

from platoon_harness.extensions import (
    DRIVERS,
    EXTENSIONS,
    Component,
    Installed,
    NotInstalled,
    check_installed,
    discover,
    find,
    load,
)
from platoon_harness.schema import ConfigError
from platoon_harness.team import Capabilities, Role, Team, team_check
from platoon_harness.topology import Topology

BALLOT = """
from platoon_harness.kernel import Extension
from platoon_harness.topology import Topology

def hub(center: str) -> Topology:
    return Topology(edges={center: ["human"]})

extension = Extension("ballot", presets=[hub])
"""


def test_discovery_reads_metadata_and_imports_nothing(site):
    site.module("never_imported_a", "raise RuntimeError('imported')")
    site.install("ballot", entry_points={EXTENSIONS: {"ballot": "never_imported_a:extension"}})
    assert [c.name for c in discover() if c.value == "never_imported_a:extension"] == ["ballot"]
    assert "never_imported_a" not in sys.modules


def test_both_groups_are_read_and_no_others(site):
    site.install(
        "kit",
        entry_points={DRIVERS: {"d": "kit:D"}, EXTENSIONS: {"e": "kit:E"}, "console_scripts": {"kit": "kit:main"}},
    )
    found = {(c.group, c.name) for c in discover() if c.distribution == "kit"}
    assert found == {(DRIVERS, "d"), (EXTENSIONS, "e")}


def test_a_component_records_its_provenance(site):
    site.install(
        "ballot",
        "2.4.6",
        entry_points={EXTENSIONS: {"ballot": "b:extension"}},
        requires=("platoon-harness>=0.1,<0.2",),
    )
    assert find(EXTENSIONS, "ballot") == Component(
        EXTENSIONS, "ballot", "b:extension", "ballot", "2.4.6", (">=0.1,<0.2",)
    )


def test_duplicates_are_caught_from_metadata_before_any_import(site):
    site.module("never_imported_b", "raise RuntimeError('imported')")
    site.install("one", entry_points={EXTENSIONS: {"ballot": "never_imported_b:a"}})
    site.install("two", entry_points={EXTENSIONS: {"ballot": "never_imported_b:b"}})
    problems = check_installed()
    assert any("more than one distribution: one 1.0.0, two 1.0.0" in str(problem) for problem in problems)
    with pytest.raises(ConfigError, match="more than one distribution"):
        load(EXTENSIONS, "ballot")
    assert "never_imported_b" not in sys.modules


def test_one_name_in_each_group_is_no_duplicate(site):
    site.install("kit", entry_points={DRIVERS: {"same": "kit:D"}, EXTENSIONS: {"same": "kit:E"}})
    assert check_installed() == ()


def test_one_distribution_found_twice_is_no_duplicate(site, tmp_path, monkeypatch):
    site.install("kit", entry_points={EXTENSIONS: {"same": "kit:E"}})
    monkeypatch.syspath_prepend(tmp_path)
    assert check_installed() == ()
    assert find(EXTENSIONS, "same").distribution == "kit"


def test_a_version_chooses_between_duplicates(site):
    site.install("one", "1.2.0", entry_points={EXTENSIONS: {"ballot": "one:e"}})
    site.install("two", "2.0.0", entry_points={EXTENSIONS: {"ballot": "two:e"}})
    assert find(EXTENSIONS, "ballot@2").distribution == "two"
    assert find(EXTENSIONS, "ballot@1.2.0").distribution == "one"


def test_a_version_matches_at_dots(site):
    site.install("one", "2.4.6", entry_points={EXTENSIONS: {"ballot": "one:e"}})
    assert find(EXTENSIONS, "ballot@2.4").version == "2.4.6"
    with pytest.raises(NotInstalled):
        find(EXTENSIONS, "ballot@2.")
    with pytest.raises(NotInstalled):
        find(EXTENSIONS, "ballot@22")


def test_an_incompatible_requirement_is_caught_before_import(site):
    site.module("never_imported_c", "raise RuntimeError('imported')")
    site.install(
        "old",
        entry_points={EXTENSIONS: {"old": "never_imported_c:e"}},
        requires=("platoon-harness>=9,<10",),
    )
    assert any("needs platoon-harness>=9,<10" in str(problem) for problem in check_installed())
    with pytest.raises(ConfigError, match="needs platoon-harness>=9,<10"):
        load(EXTENSIONS, "old")
    assert "never_imported_c" not in sys.modules


@pytest.mark.parametrize(
    "requirement",
    [
        "platoon-harness",
        "platoon-harness>=0.1,<0.2",
        "platoon_harness>=0.1",
        "Platoon.Harness==0.1.*",
        "platoon-harness~=0.1.0",
        "platoon-harness!=0.2",
        "platoon-harness<1",
        "platoon-harness==0.1",
        "platoon-harness (>=0.1)",
        "platoon-harness[cli]>=0.1",
        "platoon-harness>=9; extra == 'future'",
        "something-else>=9",
        "platoon-harness-sdk>=9",
    ],
)
def test_requirements_this_sdk_meets(site, requirement):
    site.install("ok", entry_points={EXTENSIONS: {"ok": "ok:e"}}, requires=(requirement,))
    assert check_installed() == ()


@pytest.mark.parametrize(
    "requirement",
    [
        "platoon-harness>=0.2",
        "platoon-harness<0.1",
        "platoon-harness==0.2.*",
        "platoon-harness!=0.1.*",
        "platoon-harness~=0.2.0",
        "platoon-harness>0.1.0",
        "platoon-harness<=0.0.9",
        "platoon-harness>=9 ; python_version >= '3'",
        "Platoon.Harness>=9",
    ],
)
def test_requirements_this_sdk_fails(site, requirement):
    site.install("bad", entry_points={EXTENSIONS: {"bad": "bad:e"}}, requires=(requirement,))
    assert len(check_installed()) == 1


def test_a_requirement_we_cannot_read_is_a_problem_not_a_pass(site):
    site.install(
        "odd", entry_points={EXTENSIONS: {"odd": "odd:e"}}, requires=("platoon-harness @ https://x.test/a.whl",)
    )
    assert "unreadable SDK requirement" in str(check_installed()[0])


def test_load_imports_exactly_the_named_component(site):
    site.module("loaded_ballot", BALLOT)
    site.module("never_imported_d", "raise RuntimeError('imported')")
    site.install("ballot", entry_points={EXTENSIONS: {"ballot": "loaded_ballot:extension"}})
    site.install("other", entry_points={EXTENSIONS: {"other": "never_imported_d:extension"}})
    assert load(EXTENSIONS, "ballot").name == "ballot"
    assert "never_imported_d" not in sys.modules


def test_module_attr_is_always_accepted(site):
    site.module("loose_ballot", BALLOT)
    assert load(EXTENSIONS, "loose_ballot:extension").name == "ballot"
    assert find(EXTENSIONS, "loose_ballot:extension").distribution is None


def test_an_unknown_name_lists_registered_installed_and_nearest(site):
    site.install("platoon-harness-ballot", "0.2.0", entry_points={EXTENSIONS: {"ballot": "b:e"}})
    site.install("platoon-harness-board", "0.3.0", entry_points={EXTENSIONS: {"bored": "b:e"}})
    with pytest.raises(NotInstalled) as caught:
        load(EXTENSIONS, "balot")
    text = str(caught.value)
    assert text.startswith("extensions.balot: no extension")
    assert "no extension `balot`. Did you mean `ballot`?" in text
    assert "Registered: ballot, bored, bwrap." in text
    assert "platoon-harness-ballot 0.2.0" in text
    assert "platoon-harness-board 0.3.0" in text


def test_a_missing_version_lists_the_versions_there_are(site):
    site.install("ballot", "1.0.0", entry_points={EXTENSIONS: {"ballot": "b:e"}})
    with pytest.raises(NotInstalled, match=r"Registered: ballot 1\.0\.0"):
        find(EXTENSIONS, "ballot@2")


def test_a_failed_import_is_a_problem_named_for_its_component(site):
    site.module("broken_ballot", "raise RuntimeError('boom')")
    site.install("ballot", entry_points={EXTENSIONS: {"ballot": "broken_ballot:extension"}})
    with pytest.raises(ConfigError, match="could not import `broken_ballot:extension`: boom"):
        load(EXTENSIONS, "ballot")


def test_something_else_in_the_extensions_group_is_refused(site):
    site.module("not_ballot", "extension = 3")
    site.install("ballot", entry_points={EXTENSIONS: {"ballot": "not_ballot:extension"}})
    with pytest.raises(ConfigError, match="is not an Extension"):
        load(EXTENSIONS, "ballot")


def test_installed_lists_without_importing(site):
    site.module("never_imported_e", "raise RuntimeError('imported')")
    site.install("ballot", entry_points={EXTENSIONS: {"ballot": "never_imported_e:extension"}})
    assert list(Installed()) == ["ballot", "bwrap"]
    assert len(Installed()) == 2
    assert "never_imported_e" not in sys.modules


def test_installed_says_a_name_is_missing_the_way_a_mapping_does(site):
    assert "ghost" not in Installed()
    assert Installed().get("ghost") is None


def test_installing_activates_nothing(site):
    site.module("never_imported_f", "raise RuntimeError('imported')")
    site.install("ballot", entry_points={EXTENSIONS: {"ballot": "never_imported_f:extension"}})
    with pytest.raises(ConfigError, match="unknown preset `hub`"):
        Team.loads('[roles.a]\nharness = "pi"\n[topology.hub]\ncenter = "a"')
    assert "never_imported_f" not in sys.modules


def test_a_named_extensions_preset_works_from_metadata_to_grants(site):
    site.module("installed_ballot", BALLOT)
    site.install("ballot", entry_points={EXTENSIONS: {"ballot": "installed_ballot:extension"}})
    team = Team.loads('extensions = ["ballot"]\n[roles.a]\nharness = "pi"\n[topology.hub]\ncenter = "a"')
    assert team_check(team, capabilities={"pi": Capabilities(persistent=True)}, extensions=Installed()) == ()
    assert team.resolved(Installed()).topology == Topology(edges={"a": ["human"]})


def test_team_check_reports_what_loading_an_extension_found(site):
    site.install("old", entry_points={EXTENSIONS: {"old": "old:e"}}, requires=("platoon-harness>=9",))
    team = Team(roles={"a": Role(harness="pi")}, extensions=["old", "ghost"])
    report = team_check(team, capabilities={"pi": Capabilities(persistent=True)}, extensions=Installed())
    found = "\n".join(map(str, report))
    assert "needs platoon-harness>=9" in found
    assert "no extension `ghost`" in found
    assert "Registered: bwrap, old." in found


def test_drivers_load_by_name_too(site):
    site.module("a_driver", "class Driver: ...")
    site.install("kit", entry_points={DRIVERS: {"mine": "a_driver:Driver"}})
    assert load(DRIVERS, "mine").__name__ == "Driver"
    with pytest.raises(NotInstalled, match="no driver `other`"):
        load(DRIVERS, "other")


def test_a_module_reference_works_with_nothing_installed(site):
    site.module(
        "nothing_installed_ext", 'from platoon_harness.kernel import Extension\nextension = Extension("loose")\n'
    )
    assert list(Installed()) == ["bwrap"]
    team = Team.loads('extensions = ["nothing_installed_ext:extension"]\n[roles.a]\nharness = "pi"\n')

    assert team.resolved(Installed()) == team
    assert team_check(team, capabilities={"pi": Capabilities(persistent=True)}, extensions=Installed()) == ()
