import argparse
import json
from getpass import getpass
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="ZELA · triagem de relatos urbanos")
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("dataset", help="recriar a base sintética")
    subcommands.add_parser("train", help="treinar e avaliar os modelos")
    predict = subcommands.add_parser("predict", help="classificar um relato")
    predict.add_argument("text")
    serve = subcommands.add_parser("serve", help="abrir o ZELA neste computador")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--exemplo", action="store_true", help="usar um bairro fictício separado")
    serve.add_argument(
        "--equipe", action="store_true", help="definir a senha da equipe nesta sessão"
    )
    backup = subcommands.add_parser("backup", help="copiar o banco local para outro arquivo")
    backup.add_argument("destino", type=Path)
    backup.add_argument("--exemplo", action="store_true")
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

        from zela_ml.api import create_app

        password = getpass("Senha da equipe: ") if args.equipe else None
        if args.equipe and not 12 <= len(password) <= 256:
            parser.exit(1, "Escolha uma senha de 12 a 256 caracteres.\n")
        uvicorn.run(
            create_app(demo=args.exemplo, team_password=password), host="127.0.0.1", port=args.port
        )
    elif args.command == "backup":
        from zela_ml.settings import INSTANCE
        from zela_ml.zeladoria import Occurrences

        filename = "zela-exemplo.sqlite3" if args.exemplo else "zela.sqlite3"
        source = INSTANCE / filename
        if not source.is_file():
            parser.exit(1, "Nenhum banco local encontrado.\n")
        try:
            Occurrences(source).backup(args.destino)
        except (ValueError, OSError) as error:
            parser.exit(1, f"Não foi possível salvar a cópia: {error}\n")
        print("Cópia salva.")


if __name__ == "__main__":
    main()
