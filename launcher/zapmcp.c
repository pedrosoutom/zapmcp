// Lançador do ZapMCP para o Claude Desktop.
//
// O macOS atribui o acesso a dados protegidos (a pasta do WhatsApp) ao processo "responsável".
// O Claude Desktop inicia a extensão com o comando do manifest como responsável por si mesmo;
// se esse comando for o uv, é o uv que aparece pedindo permissão e que precisa do Acesso Total
// ao Disco. Este lançador fica no lugar dele: inicia o uv como filho (o uv e o Python herdam a
// responsabilidade) e espera. Assim a permissão é dada a este programa, e não ao uv.
//
// Uso: zapmcp <argumentos do uv>, ex.: zapmcp run --directory DIR zapmcp serve
// Não escreve nada no stdout: ele é o canal do protocolo MCP, herdado direto pelo servidor.

#include <errno.h>
#include <signal.h>
#include <spawn.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/wait.h>
#include <unistd.h>

extern char **environ;

static pid_t child = 0;

static void forward(int sig) {
    if (child > 0) kill(child, sig);
}

// Onde procurar o uv quando ele não está no PATH (o Claude Desktop não herda o PATH do shell).
static const char *uv_candidates[] = {
    "/opt/homebrew/bin/uv",
    "/usr/local/bin/uv",
    "~/.local/bin/uv",
    "~/.cargo/bin/uv",
};

static int find_uv(char *out, size_t size) {
    const char *custom = getenv("ZAPMCP_UV");
    if (custom && *custom) {
        snprintf(out, size, "%s", custom);
        return access(out, X_OK) == 0;
    }
    const char *path = getenv("PATH");
    if (path) {
        char *copy = strdup(path), *rest = copy, *dir;
        while ((dir = strsep(&rest, ":"))) {
            if (!*dir) continue;
            snprintf(out, size, "%s/uv", dir);
            if (access(out, X_OK) == 0) {
                free(copy);
                return 1;
            }
        }
        free(copy);
    }
    const char *home = getenv("HOME");
    for (size_t i = 0; i < sizeof uv_candidates / sizeof *uv_candidates; i++) {
        const char *c = uv_candidates[i];
        if (c[0] == '~') {
            if (!home) continue;
            snprintf(out, size, "%s%s", home, c + 1);
        } else {
            snprintf(out, size, "%s", c);
        }
        if (access(out, X_OK) == 0) return 1;
    }
    return 0;
}

int main(int argc, char **argv) {
    char uv[4096];
    if (!find_uv(uv, sizeof uv)) {
        fprintf(stderr, "zapmcp: não encontrei o uv. Instale com `brew install uv` ou defina ZAPMCP_UV.\n");
        return 127;
    }

    char **args = calloc((size_t)argc + 1, sizeof *args);
    args[0] = uv;
    for (int i = 1; i < argc; i++) args[i] = argv[i];

    struct sigaction sa = {0};
    sa.sa_handler = forward;
    sigemptyset(&sa.sa_mask);
    sigaction(SIGTERM, &sa, NULL);
    sigaction(SIGINT, &sa, NULL);
    sigaction(SIGHUP, &sa, NULL);

    int err = posix_spawn(&child, uv, NULL, NULL, args, environ);
    if (err) {
        fprintf(stderr, "zapmcp: não consegui iniciar %s: %s\n", uv, strerror(err));
        return 126;
    }

    int status;
    while (waitpid(child, &status, 0) < 0) {
        if (errno != EINTR) return 1;
    }
    if (WIFEXITED(status)) return WEXITSTATUS(status);
    if (WIFSIGNALED(status)) return 128 + WTERMSIG(status);
    return 1;
}
