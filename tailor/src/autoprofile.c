#include "tailor/profile.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int env_enabled(const char *name) {
    const char *v = getenv(name);
    return v && *v && strcmp(v, "0") != 0 && strcmp(v, "false") != 0;
}

__attribute__((constructor))
static void tailor_autoprofile_init(void) {
    const char *out_path = getenv("TAILOR_PROFILE_OUT");
    if (!out_path || !*out_path) {
        return;
    }

    unsigned collect_flags = 0;
    unsigned write_flags = TAILOR_PROFILE_WRITE_NAMES;
    if (!env_enabled("TAILOR_PROFILE_ALL_MODULES") && env_enabled("TAILOR_PROFILE_SYSTEM_ONLY")) {
        collect_flags |= TAILOR_PROFILE_SYSTEM_ONLY;
    }
    if (env_enabled("TAILOR_PROFILE_RAW_SYMBOL_NAMES")) {
        collect_flags |= TAILOR_PROFILE_RAW_SYMBOL_NAMES;
    }
    if (env_enabled("TAILOR_PROFILE_ADDRESSES")) {
        write_flags |= TAILOR_PROFILE_WRITE_ADDRESSES;
    }
    if (env_enabled("TAILOR_PROFILE_NO_NAMES")) {
        write_flags &= ~TAILOR_PROFILE_WRITE_NAMES;
    }

    tailor_profile profile;
    tailor_profile_init(&profile);
    if (tailor_profile_collect(&profile, collect_flags) < 0) {
        return;
    }

    FILE *f = fopen(out_path, "w");
    if (f) {
        (void)tailor_profile_write_json(f, &profile, write_flags);
        fclose(f);
    }
    tailor_profile_free(&profile);
}
