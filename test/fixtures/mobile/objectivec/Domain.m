#import "Domain.h"
@implementation Root
@end
@implementation MemoryRepository
- (int)fetch { return self.prefix; }
@end
@implementation Unrelated
- (int)fetch { return 7; }
@end
