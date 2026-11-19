namespace Zela.CitizenTech.Models;

public sealed class OcorrenciaPavimentacao : Ocorrencia
{
    public override string Categoria => "Pavimentação";
    public override string OrientacaoParaEquipe => "Inspecionar o trecho e avaliar o risco para pedestres e veículos.";

    public OcorrenciaPavimentacao(string protocolo, string descricao, Endereco endereco)
        : base(protocolo, descricao, endereco)
    {
    }
}
