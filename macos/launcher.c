// STT-Clean.app's executable. Starts stt_clean.py as a child process (not exec), so macOS
// attributes the Microphone and Accessibility permissions to STT-Clean.app, not to Python.
// PYTHON, HF_HOME, SCRIPT and LOG are set by build_app.sh.
#include <fcntl.h>
#include <spawn.h>
#include <stdlib.h>
#include <sys/wait.h>

extern char **environ;

int main(void) {
    setenv("HF_HUB_OFFLINE", "1", 1);   // Finder-launched apps don't read ~/.zshrc
    setenv("HF_HOME", HF_HOME, 1);      // where the speech models already on this Mac are
    posix_spawn_file_actions_t io;      // stdout + stderr -> log file (overwritten on each launch)
    posix_spawn_file_actions_init(&io);
    posix_spawn_file_actions_addopen(&io, 1, LOG, O_WRONLY | O_CREAT | O_TRUNC, 0644);
    posix_spawn_file_actions_adddup2(&io, 1, 2);
    char *argv[] = {PYTHON, "-u", SCRIPT, NULL};
    pid_t pid;
    int st;
    if (posix_spawn(&pid, PYTHON, &io, NULL, argv, environ) != 0)
        return 1;
    waitpid(pid, &st, 0);
    return WIFEXITED(st) ? WEXITSTATUS(st) : 1;
}
