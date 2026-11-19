using Zela.CitizenTech.ConsoleUi;
using Zela.CitizenTech.Services;

namespace Zela.CitizenTech;

internal static class Program
{
    private static void Main()
    {
        var central = new CentralDeAtendimento();
        var aplicacao = new AplicacaoConsole(central);
        aplicacao.Executar();
    }
}
