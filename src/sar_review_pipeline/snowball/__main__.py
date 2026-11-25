"""Etapas 01 e 02 de uma rodada: coleta (backward e forward juntos) e triagem por título."""
import sys

USAGE = "uso: step01-snowball start [--force] | round N [--no-s2]"


def main():
    # uv run step01-snowball start             -> rodada 0: busca o start set (--force busca de novo)
    # uv run step01-snowball round 1           -> rodada 1: backward e forward do start set + triagem por título
    # uv run step01-snowball round N           -> rodada N: seeds = r<N-1>/selected.jsonl (texto completo)
    # uv run step01-snowball round N --no-s2   -> forward só com o OpenAlex
    args = sys.argv[1:]
    if args and args[0] == "start":
        from sar_review_pipeline.snowball.collect import fetch_start_set

        works = fetch_start_set(force="--force" in args)
        print(f"Start set: {len(works)} works")
        return
    if len(args) >= 2 and args[0] == "round" and args[1].isdigit() and int(args[1]) >= 1:
        from sar_review_pipeline.rounds import Round
        from sar_review_pipeline.screening import screening
        from sar_review_pipeline.snowball.collect import RoundCollector

        rnd = Round(int(args[1]))
        works = RoundCollector(rnd, use_s2="--no-s2" not in args).run()
        if not works:
            return
        screening.run(rnd)
        screening.filter(rnd)
        screening.print_summary(rnd)
        return
    sys.exit(USAGE)


if __name__ == "__main__":
    main()
