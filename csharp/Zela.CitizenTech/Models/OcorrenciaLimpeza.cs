namespace Zela.CitizenTech.Models;

public sealed class OcorrenciaLimpeza : Ocorrencia
{
    public override string Categoria => "Limpeza urbana";
    public override string OrientacaoParaEquipe => "Avaliar o volume, o tipo de resíduo e a necessidade de coleta.";

    public OcorrenciaLimpeza(string protocolo, string descricao, Endereco endereco)
        : base(protocolo, descricao, endereco)
    {
    }
}
