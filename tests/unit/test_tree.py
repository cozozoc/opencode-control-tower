from octower.discovery.tree import SessionTree
from octower.models import SessionNode


def test_tree_recursively_attaches_children_added_before_and_after_parent() -> None:
    tree = SessionTree("root")
    tree.add(SessionNode("grandchild", "child"))
    tree.add(SessionNode("child", "root"))
    tree.add(SessionNode("root"))
    tree.add(SessionNode("late-child", "root"))

    assert [node.session_id for node in tree.descendants()] == ["child", "grandchild", "late-child"]
