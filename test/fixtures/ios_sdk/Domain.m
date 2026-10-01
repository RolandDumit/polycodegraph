#import "Domain.h"
@implementation ObjCRepository
- (int)fetch { return 42; }
@end
@implementation ProductViewController
- (int)reload:(ObjCRepository *)repository { return [repository fetch]; }
@end
