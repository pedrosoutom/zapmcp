// Pedido de liberação do ZapMCP: mostra o diálogo do sistema (Touch ID, ou a senha do Mac quando não
// há sensor) e sai 0 se o dono confirmou, 1 se cancelou ou negou, 2 se não há como autenticar.
// Nada vai para o stdout: o servidor MCP usa o stdout para o protocolo.
import Foundation
import LocalAuthentication

let mensagem = CommandLine.arguments.count > 1 ? CommandLine.arguments[1] : "Um agente quer ler o WhatsApp."
let contexto = LAContext()
contexto.localizedCancelTitle = "Negar"
var erro: NSError?
guard contexto.canEvaluatePolicy(.deviceOwnerAuthentication, error: &erro) else {
    FileHandle.standardError.write(("sem autenticação disponível: " + (erro?.localizedDescription ?? "?") + "\n").data(using: .utf8)!)
    exit(2)
}
let semaforo = DispatchSemaphore(value: 0)
var codigo: Int32 = 1
contexto.evaluatePolicy(.deviceOwnerAuthentication, localizedReason: mensagem) { ok, falha in
    if ok {
        codigo = 0
    } else if let falha = falha {
        FileHandle.standardError.write((falha.localizedDescription + "\n").data(using: .utf8)!)
    }
    semaforo.signal()
}
semaforo.wait()
exit(codigo)
