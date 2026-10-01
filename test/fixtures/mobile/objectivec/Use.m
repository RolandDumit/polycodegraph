#import "Domain.h"
int load(id<Repository> repository) { return [repository fetch]; }
int concrete(MemoryRepository *repository) { return [repository fetch]; }
