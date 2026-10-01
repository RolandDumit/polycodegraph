import UIKit
protocol SwiftRepository { func fetch() -> String }
class Screen: UIViewController {
    func reload(_ repository: any SwiftRepository) -> String { repository.fetch() }
}
func bridge(_ repository: ObjCRepository) -> Int32 { repository.fetch() }
