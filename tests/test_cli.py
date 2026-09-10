from taskx.cli import build_parser


def test_parser_accepts_json_after_subcommand_arguments() -> None:
    args = build_parser().parse_args(["show", "deadbeef", "--json"])

    assert args.command == "show"
    assert args.uuid == "deadbeef"
    assert args.json_output is True
