# ZELA · C# Software Development

**Global Solution 2026 · CitizenTech · FIAP**

## Integrantes

- Erik Kaiyu Suguiyama · RM 559273
- Guilherme Vital · RM 560073
- Kayque Carvalho · RM 561189

## A solução

Esta aplicação de console registra necessidades de iluminação pública, limpeza urbana e pavimentação. O morador informa o relato e o endereço, recebe um protocolo e pode acompanhar o status durante a sessão.

## Executar

Requer o .NET SDK 8.0 ou superior. A partir da raiz do repositório:

```sh
dotnet run --project csharp/Zela.CitizenTech/Zela.CitizenTech.csproj
```

No menu, escolha **1** para registrar um relato, **2** para listar as ocorrências da sessão, **3** para avançar o status pelo protocolo e **0** para sair.

## Organização e POO

- `Zela.CitizenTech/Models/Endereco.cs` encapsula rua, número e bairro e valida os campos obrigatórios.
- `Zela.CitizenTech/Models/Ocorrencia.cs` é a classe base abstrata. Guarda protocolo, relato, endereço e status com propriedades de escrita privada.
- `OcorrenciaIluminacao`, `OcorrenciaLimpeza` e `OcorrenciaPavimentacao` herdam da classe base e sobrescrevem categoria e orientação de triagem.
- `Zela.CitizenTech/Services/CentralDeAtendimento.cs` mantém a coleção privada, cria protocolos e oferece uma cópia da lista para consulta.
- `Zela.CitizenTech/ConsoleUi/AplicacaoConsole.cs` organiza o menu e percorre objetos pelo tipo `Ocorrencia`; cada subclasse apresenta sua categoria e orientação, demonstrando polimorfismo.

A aplicação não usa banco de dados. Os registros ficam em memória e são apagados quando o programa fecha.

## Evidência de funcionamento

A [execução demonstrativa](evidencias/execucao-demo.txt) registra três categorias, lista os protocolos e avança um atendimento. A [entrada da demonstração](evidencias/entrada-demo.txt) permite reproduzi-la:

```sh
dotnet run --project csharp/Zela.CitizenTech/Zela.CitizenTech.csproj < csharp/evidencias/entrada-demo.txt
```

Os dados da demonstração são fictícios. Veja o [README das evidências](evidencias/README.md) para mais detalhes.
