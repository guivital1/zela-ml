namespace Zela.CitizenTech.Models;

public sealed class Endereco
{
    public string Rua { get; private set; }
    public string Numero { get; private set; }
    public string Bairro { get; private set; }

    public Endereco(string rua, string numero, string bairro)
    {
        Rua = ValidarCampo(rua, "rua");
        Numero = ValidarCampo(numero, "número");
        Bairro = ValidarCampo(bairro, "bairro");
    }

    public string Exibir()
    {
        return $"{Rua}, {Numero} · {Bairro}";
    }

    private static string ValidarCampo(string valor, string nome)
    {
        if (string.IsNullOrWhiteSpace(valor))
        {
            throw new ArgumentException($"Informe {nome}.", nameof(valor));
        }

        return valor.Trim();
    }
}
