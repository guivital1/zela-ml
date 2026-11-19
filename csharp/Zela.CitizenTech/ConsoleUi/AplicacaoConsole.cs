using Zela.CitizenTech.Models;
using Zela.CitizenTech.Services;

namespace Zela.CitizenTech.ConsoleUi;

public sealed class AplicacaoConsole
{
    private readonly CentralDeAtendimento _central;

    public AplicacaoConsole(CentralDeAtendimento central)
    {
        _central = central ?? throw new ArgumentNullException(nameof(central));
    }

    public void Executar()
    {
        bool continuar = true;

        while (continuar)
        {
            ExibirCabecalho();
            ExibirMenu();
            string? opcao = Console.ReadLine();

            switch (opcao)
            {
                case "1": RegistrarOcorrencia(); break;
                case "2": ListarOcorrencias(); break;
                case "3": AvancarStatus(); break;
                case "0": continuar = false; break;
                default: Console.WriteLine("Escolha uma opção do menu."); break;
            }

            if (continuar)
            {
                Console.WriteLine("\nPressione Enter para continuar.");
                Console.ReadLine();
            }
        }

        Console.WriteLine("\nObrigado por usar o ZELA. Até a próxima!");
    }

    private static void ExibirCabecalho()
    {
        Console.WriteLine("\n╭────────────────────────────────────────────╮");
        Console.WriteLine("│                    ZELA                    │");
        Console.WriteLine("│       Cuidado com a rua começa aqui        │");
        Console.WriteLine("╰────────────────────────────────────────────╯");
    }

    private static void ExibirMenu()
    {
        Console.WriteLine("1. Registrar uma necessidade da rua");
        Console.WriteLine("2. Acompanhar ocorrências desta sessão");
        Console.WriteLine("3. Avançar o atendimento de uma ocorrência");
        Console.WriteLine("0. Sair");
        Console.Write("\nO que você gostaria de fazer? ");
    }

    private void RegistrarOcorrencia()
    {
        Console.WriteLine("\nQual situação você quer registrar?");
        Console.WriteLine("1. Iluminação pública");
        Console.WriteLine("2. Limpeza urbana");
        Console.WriteLine("3. Pavimentação");
        Console.Write("Categoria: ");
        string? categoria = Console.ReadLine();

        if (categoria != "1" && categoria != "2" && categoria != "3")
        {
            Console.WriteLine("Categoria não reconhecida. O relato não foi registrado.");
            return;
        }

        string descricao = LerCampo("Conte o que está acontecendo");
        string rua = LerCampo("Rua");
        string numero = LerCampo("Número (ou s/n)");
        string bairro = LerCampo("Bairro");

        var endereco = new Endereco(rua, numero, bairro);
        Ocorrencia ocorrencia;
        if (categoria == "1")
        {
            ocorrencia = _central.RegistrarIluminacao(descricao, endereco);
        }
        else if (categoria == "2")
        {
            ocorrencia = _central.RegistrarLimpeza(descricao, endereco);
        }
        else
        {
            ocorrencia = _central.RegistrarPavimentacao(descricao, endereco);
        }

        Console.WriteLine("\nPronto. Seu relato foi registrado.");
        Console.WriteLine($"Protocolo: {ocorrencia.Protocolo}");
        Console.WriteLine($"Local: {ocorrencia.Endereco.Exibir()}");
        Console.WriteLine("O protocolo fica disponível enquanto esta aplicação estiver aberta.");
    }

    private void ListarOcorrencias()
    {
        List<Ocorrencia> ocorrencias = _central.Listar();

        if (ocorrencias.Count == 0)
        {
            Console.WriteLine("\nNenhum relato foi registrado nesta sessão.");
            return;
        }

        Console.WriteLine($"\n{ocorrencias.Count} ocorrência(s) nesta sessão");
        Console.WriteLine("──────────────────────────────────────────────");

        foreach (Ocorrencia ocorrencia in ocorrencias)
        {
            // A lista é do tipo base; cada subclasse fornece sua categoria e orientação.
            Console.WriteLine(ocorrencia.Resumo());
            Console.WriteLine("──────────────────────────────────────────────");
        }
    }

    private void AvancarStatus()
    {
        if (_central.Quantidade == 0)
        {
            Console.WriteLine("\nRegistre uma ocorrência antes de atualizar o atendimento.");
            return;
        }

        Console.Write("\nInforme o protocolo: ");
        string protocolo = Console.ReadLine()?.Trim() ?? string.Empty;
        Ocorrencia? ocorrencia = _central.BuscarPorProtocolo(protocolo);

        if (ocorrencia is null)
        {
            Console.WriteLine("Não encontrei esse protocolo nesta sessão.");
            return;
        }

        try
        {
            ocorrencia.AvancarStatus();
            Console.WriteLine($"Atendimento atualizado: {ocorrencia.StatusExibicao}.");
        }
        catch (InvalidOperationException erro)
        {
            Console.WriteLine(erro.Message);
        }
    }

    private static string LerCampo(string pergunta)
    {
        while (true)
        {
            Console.Write($"{pergunta}: ");
            string? valor = Console.ReadLine();

            if (!string.IsNullOrWhiteSpace(valor))
            {
                return valor.Trim();
            }

            Console.WriteLine("Esse campo precisa ser preenchido.");
        }
    }
}
