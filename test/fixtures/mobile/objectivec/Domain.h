#ifndef DOMAIN_H
#define DOMAIN_H
@protocol Repository
- (int)fetch;
@end
__attribute__((objc_root_class))
@interface Root
@end
@interface MemoryRepository : Root <Repository>
@property(nonatomic, assign) int prefix;
- (int)fetch;
@end
@interface Unrelated : Root
- (int)fetch;
@end
int load(id<Repository> repository);
#endif
