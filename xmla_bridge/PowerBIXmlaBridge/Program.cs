using System.Data;
using System.Text.Json;
using System.Text.Json.Serialization;
using AnalysisServicesAccessToken = Microsoft.AnalysisServices.AccessToken;
using AmoServer = Microsoft.AnalysisServices.Server;
using Microsoft.AnalysisServices.AdomdClient;

var options = new JsonSerializerOptions
{
    PropertyNameCaseInsensitive = true,
    PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
    DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull
};

try
{
    using var input = new StreamReader(Console.OpenStandardInput());
    var requestJson = await input.ReadToEndAsync();
    var request = JsonSerializer.Deserialize<BridgeRequest>(requestJson, options)
        ?? throw new InvalidOperationException("Missing bridge request payload.");

    BridgeResponse response = request.Command switch
    {
        "attach" => Attach(request),
        "query" => Query(request),
        "execute" => Execute(request),
        _ => BridgeResponse.Fail($"Unsupported XMLA bridge command: {request.Command}")
    };

    Console.Write(JsonSerializer.Serialize(response, options));
}
catch (Exception error)
{
    Console.Write(JsonSerializer.Serialize(BridgeResponse.Fail(error.Message), options));
}

static BridgeResponse Attach(BridgeRequest request)
{
    using var connection = CreateAdomdConnection(request);
    connection.Open();
    return BridgeResponse.Ok(new Dictionary<string, object?>
    {
        ["serverVersion"] = connection.ServerVersion,
        ["database"] = connection.Database,
        ["state"] = connection.State.ToString()
    });
}

static BridgeResponse Query(BridgeRequest request)
{
    using var connection = CreateAdomdConnection(request);
    connection.Open();
    using var command = connection.CreateCommand();
    command.CommandText = Require(request.Query, "query");

    using var reader = command.ExecuteReader();
    var columns = Enumerable.Range(0, reader.FieldCount)
        .Select(reader.GetName)
        .ToList();
    var rows = new List<Dictionary<string, object?>>();
    var maxRows = request.MaxRows is > 0 ? request.MaxRows.Value : 500;
    var totalRows = 0;

    while (reader.Read())
    {
        totalRows++;
        if (rows.Count >= maxRows)
        {
            continue;
        }

        var row = new Dictionary<string, object?>();
        for (var index = 0; index < reader.FieldCount; index++)
        {
            var value = reader.GetValue(index);
            row[columns[index]] = value == DBNull.Value ? null : value;
        }
        rows.Add(row);
    }

    return BridgeResponse.Ok(new Dictionary<string, object?>
    {
        ["columns"] = columns,
        ["rows"] = rows,
        ["rowCount"] = totalRows,
        ["truncated"] = totalRows > rows.Count
    });
}

static BridgeResponse Execute(BridgeRequest request)
{
    using var server = new AmoServer();
    server.AccessToken = new AnalysisServicesAccessToken(
        Require(request.AccessToken, "accessToken"),
        Expiration(request.AccessTokenExpiresAt)
    );
    server.Connect(ConnectionString(request));
    try
    {
        var results = server.Execute(Require(request.CommandText, "commandText"));
        return BridgeResponse.Ok(new Dictionary<string, object?>
        {
            ["executed"] = true,
            ["messages"] = XmlaMessages(results),
            ["results"] = XmlaResults(results)
        });
    }
    finally
    {
        server.Disconnect();
    }
}

static AdomdConnection CreateAdomdConnection(BridgeRequest request)
{
    var connection = new AdomdConnection(ConnectionString(request))
    {
        AccessToken = new AnalysisServicesAccessToken(
            Require(request.AccessToken, "accessToken"),
            Expiration(request.AccessTokenExpiresAt)
        )
    };
    return connection;
}

static string ConnectionString(BridgeRequest request)
{
    return $"Data Source={Require(request.ServerUrl, "serverUrl")};Initial Catalog={Require(request.InitialCatalog, "initialCatalog")};";
}

static DateTimeOffset Expiration(long? epochMilliseconds)
{
    return epochMilliseconds is > 0
        ? DateTimeOffset.FromUnixTimeMilliseconds(epochMilliseconds.Value)
        : DateTimeOffset.UtcNow.AddMinutes(55);
}

static string Require(string? value, string name)
{
    if (string.IsNullOrWhiteSpace(value))
    {
        throw new InvalidOperationException($"Missing required field: {name}");
    }
    return value;
}

static List<string> XmlaMessages(Microsoft.AnalysisServices.XmlaResultCollection results)
{
    var messages = new List<string>();
    foreach (Microsoft.AnalysisServices.XmlaResult result in results)
    {
        foreach (Microsoft.AnalysisServices.XmlaMessage message in result.Messages)
        {
            messages.Add(message.Description);
        }
    }
    return messages;
}

static List<Dictionary<string, object?>> XmlaResults(Microsoft.AnalysisServices.XmlaResultCollection results)
{
    var output = new List<Dictionary<string, object?>>();
    foreach (Microsoft.AnalysisServices.XmlaResult result in results)
    {
        output.Add(new Dictionary<string, object?>
        {
            ["messageCount"] = result.Messages.Count
        });
    }
    return output;
}

public sealed record BridgeRequest
{
    public string? Command { get; init; }
    public string? ServerUrl { get; init; }
    public string? InitialCatalog { get; init; }
    public string? AccessToken { get; init; }
    public long? AccessTokenExpiresAt { get; init; }
    public string? Query { get; init; }
    public string? QueryType { get; init; }
    public int? MaxRows { get; init; }
    public string? CommandText { get; init; }
    public string? CommandType { get; init; }
}

public sealed record BridgeResponse
{
    public bool Success { get; init; }
    public string? Error { get; init; }
    public Dictionary<string, object?>? Data { get; init; }

    public static BridgeResponse Ok(Dictionary<string, object?> data) => new()
    {
        Success = true,
        Data = data
    };

    public static BridgeResponse Fail(string error) => new()
    {
        Success = false,
        Error = error
    };
}
