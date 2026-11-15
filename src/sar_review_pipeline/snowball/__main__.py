import sys

USAGE = "uso: step01-snowball [backward | forward [--max-rounds N] [--no-s2]]"


def main():
    # uv run step01-snowball                         -> backward (etapas 01 e 02) até convergir
    # uv run step01-snowball forward                 -> forward (etapas 01 e 02) até convergir
    # uv run step01-snowball forward --max-rounds 1  -> forward com limite de rodadas (protocolo, 4.4)
    # uv run step01-snowball forward --no-s2         -> forward só com o OpenAlex
    args = sys.argv[1:]
    direction = args[0] if args and not args[0].startswith("--") else "backward"
    if direction == "backward" and len(args) <= 1:
        from sar_review_pipeline.snowball import backward

        backward.run()
    elif direction == "forward":
        from sar_review_pipeline.snowball import forward

        max_rounds = None
        if "--max-rounds" in args:
            i = args.index("--max-rounds")
            if i + 1 >= len(args) or not args[i + 1].isdigit():
                sys.exit(USAGE)
            max_rounds = int(args[i + 1])
        forward.run(max_rounds=max_rounds, use_s2="--no-s2" not in args)
    else:
        sys.exit(USAGE)


if __name__ == "__main__":
    main()
