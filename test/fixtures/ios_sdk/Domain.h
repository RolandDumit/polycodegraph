#import <UIKit/UIKit.h>
@interface ObjCRepository : NSObject
- (int)fetch;
@end
@interface ProductViewController : UIViewController
- (int)reload:(ObjCRepository *)repository;
@end
