using Zela.CitizenTech.Models;

namespace Zela.CitizenTech.Services;

public sealed class CentralDeAtendimento
{
    private readonly List<Ocorrencia> _ocorrencias = new();
    private int _proximoNumero = 1;

    public int Quantidade => _ocorrencias.Count;

    public Ocorrencia RegistrarIluminacao(string descricao, Endereco endereco)
    {
        var ocorrencia = new OcorrenciaIluminacao(CriarProtocolo(), descricao, endereco);
        _ocorrencias.Add(ocorrencia);
        return ocorrencia;
    }

    public Ocorrencia RegistrarLimpeza(string descricao, Endereco endereco)
    {
        var ocorrencia = new OcorrenciaLimpeza(CriarProtocolo(), descricao, endereco);
        _ocorrencias.Add(ocorrencia);
        return ocorrencia;
    }

    public Ocorrencia RegistrarPavimentacao(string descricao, Endereco endereco)
    {
        var ocorrencia = new OcorrenciaPavimentacao(CriarProtocolo(), descricao, endereco);
        _ocorrencias.Add(ocorrencia);
        return ocorrencia;
    }

    public List<Ocorrencia> Listar()
    {
        // Retorna uma cópia para que a tela não altere a coleção interna da central.
        return new List<Ocorrencia>(_ocorrencias);
    }

    public Ocorrencia? BuscarPorProtocolo(string protocolo)
    {
        foreach (Ocorrencia ocorrencia in _ocorrencias)
        {
            if (string.Equals(ocorrencia.Protocolo, protocolo.Trim(), StringComparison.OrdinalIgnoreCase))
            {
                return ocorrencia;
            }
        }

        return null;
    }

    private string CriarProtocolo()
    {
        string protocolo = $"ZL-{DateTime.Now.Year}-{_proximoNumero:D4}";
        _proximoNumero++;
        return protocolo;
    }
}
