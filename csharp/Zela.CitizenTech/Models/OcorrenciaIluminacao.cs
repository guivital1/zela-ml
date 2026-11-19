namespace Zela.CitizenTech.Models;

public sealed class OcorrenciaIluminacao : Ocorrencia
{
    public override string Categoria => "Iluminação pública";
    public override string OrientacaoParaEquipe => "Verificar o poste e a lâmpada no endereço informado.";

    public OcorrenciaIluminacao(string protocolo, string descricao, Endereco endereco)
        : base(protocolo, descricao, endereco)
    {
    }
}
