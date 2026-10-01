#import "Domain.h"
namespace detail {
struct Counter { int add(int value) { return value + 1; } };
}
int objcPlusCpp(MemoryRepository *repository) {
    detail::Counter counter;
    return counter.add([repository fetch]);
}
