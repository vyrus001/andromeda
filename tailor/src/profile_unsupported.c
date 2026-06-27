#include "tailor/profile.h"

#if !defined(__APPLE__) && !defined(__linux__)

int tailor_profile_collect(tailor_profile *profile, unsigned flags) {
    (void)profile;
    (void)flags;
    tailor_profile_set_error("tailor_profile_collect is not implemented for this platform");
    return -1;
}

#endif

