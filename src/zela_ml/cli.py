import argparse
import json


def main() -> None:
    parser = argparse.ArgumentParser(description="ZELA · triagem de relatos urbanos")
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("dataset", help="recriar a base sintética")
    subcommands.add_parser("train", help="treinar e avaliar os modelos")
    predict = subcommands.add_parser("predict", help="classificar um relato")
    predict.add_argument("text")
    serve = subcommands.add_parser("serve", help="abrir a API e a demonstração local")
    serve.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    if args.command == "dataset":
        from zela_ml.dataset import build_dataset

        frame = build_dataset()
        print(f"{len(frame)} relatos simulados · {frame['scenario'].nunique()} cenários")
    elif args.command == "train":
        from zela_ml.training import train

        metrics = train()
        print(json.dumps(metrics, ensure_ascii=False, indent=2))
    elif args.command == "predict":
        from zela_ml.inference import Classifier

        try:
            result = Classifier().predict(args.text)
        except (ValueError, FileNotFoundError) as error:
            parser.exit(1, f"{error}\n")
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.command == "serve":
        import uvicorn

        uvicorn.run("zela_ml.api:app", host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
