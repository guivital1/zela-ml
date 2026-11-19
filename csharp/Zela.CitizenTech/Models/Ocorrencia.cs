namespace Zela.CitizenTech.Models;

public abstract class Ocorrencia
{
    public string Protocolo { get; private set; }
    public string Descricao { get; private set; }
    public Endereco Endereco { get; private set; }
    public StatusOcorrencia Status { get; private set; }
    public string StatusExibicao => FormatarStatus(Status);
    public DateTime CriadaEm { get; private set; }

    public abstract string Categoria { get; }
    public abstract string OrientacaoParaEquipe { get; }

    protected Ocorrencia(string protocolo, string descricao, Endereco endereco)
    {
        if (string.IsNullOrWhiteSpace(protocolo))
        {
            throw new ArgumentException("O protocolo é obrigatório.", nameof(protocolo));
        }

        if (string.IsNullOrWhiteSpace(descricao))
        {
            throw new ArgumentException("A descrição é obrigatória.", nameof(descricao));
        }

        Protocolo = protocolo.Trim();
        Descricao = descricao.Trim();
        Endereco = endereco ?? throw new ArgumentNullException(nameof(endereco));
        Status = StatusOcorrencia.Recebida;
        CriadaEm = DateTime.Now;
    }

    public void AvancarStatus()
    {
        if (Status == StatusOcorrencia.Resolvida)
        {
            throw new InvalidOperationException("Uma ocorrência resolvida não pode avançar de status.");
        }

        Status = (StatusOcorrencia)((int)Status + 1);
    }

    public virtual string Resumo()
    {
        return $"{Protocolo} · {Categoria}\n" +
            $"Local: {Endereco.Exibir()}\n" +
            $"Relato: {Descricao}\n" +
            $"Registrada em: {CriadaEm:dd/MM/yyyy HH:mm}\n" +
            $"Status: {FormatarStatus(Status)}\n" +
            $"Triagem: {OrientacaoParaEquipe}";
    }

    private static string FormatarStatus(StatusOcorrencia status)
    {
        switch (status)
        {
            case StatusOcorrencia.Recebida:
                return "Recebida";
            case StatusOcorrencia.EmAnalise:
                return "Em análise";
            case StatusOcorrencia.Encaminhada:
                return "Encaminhada";
            case StatusOcorrencia.Resolvida:
                return "Resolvida";
            default:
                return "Indefinido";
        }
    }
}
