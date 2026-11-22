// A71Island: SpringBoard geometry for the system Dynamic Island on the Galaxy A71 (iOS 26.6.2, 23G90).
//
// The island code is in every iOS 26 SpringBoard; it turns on for MobileGestalt ArtworkDeviceSubType 2556
// (iPhone 14 Pro). That subtype alone gave the A71 a red status bar: UIKit then expects an exclusion area that the
// iPhone 11 screen type (414x896 pt) does not have. SpringBoard computes the geometry once and hands it to every app
// (UISDisplayContext), so these hooks run in SpringBoard only:
//   +[UISDisplaySingleRectShape sb_displayShapeForScreenType:]  exclusion area (points) -> DynamicSplit status bar
//   -[SBUISystemApertureLayoutMetrics sensorRegionSize]          size of the pill; compact/minimal sizes derive from it
//   -[SBUISystemApertureLayoutMetrics minimumScreenEdgeInsets]   top gap of the pill
//   -[SBUISystemApertureLayoutMetrics interSensorRegionInWindowSpace]  privacy dot position
//   +[SBHDefaultIconListLayoutProvider currentDeviceScreenType]  optional (HomeScreenType > 0): home grid type
// Approach after Viva's SpringBoard display hooks (Redmi Note 11 Pro 4G, github.com/nik300/viva-gpu); own code.
//
// Loaded by an extra LC_LOAD_DYLIB in SpringBoard (re-signed ad hoc, identifier and entitlements kept).
// Preferences: /var/mobile/Library/Preferences/org.a71.island.plist, every number optional; Enabled = NO disables.
// Log: os_log subsystem org.a71.island (reaches the USB console with sweetdtlog=SpringBoard).
#import <UIKit/UIKit.h>
#import <objc/runtime.h>
#import <objc/message.h>
#import <os/log.h>

static os_log_t ILog;
// os_log does not reach the USB console without sweetdtlog=SpringBoard: every line also goes to
// /var/mobile/Library/Caches/a71island.log (readable from TWRP), restarted at each SpringBoard launch.
static void IFile(NSString *line) {
    static FILE *f;
    if (!f) f = fopen("/var/mobile/Library/Caches/a71island.log", "w");
    if (!f) return;
    fprintf(f, "%s\n", line.UTF8String);
    fflush(f);
}
#define ILOG(fmt, ...) do { NSString *s_ = [NSString stringWithFormat:@fmt, ##__VA_ARGS__]; \
    os_log(ILog, "A71ISLAND %{public}@", s_); IFile(s_); } while (0)

// Points on the 414x896 pt screen. Apple's 2556 pill is 125 x 36.67 pt at 11.33 pt from the top; the A71 punch hole
// sits at the top centre, inside that box.
static double IScreenW = 414.0;
static double IIslandW = 125.0, IIslandH = 36.667, IIslandTop = 11.333;
static double IAvoidW = 150.0;     // status bar keeps this width free around the pill
static double IInterW = 9.0;       // privacy dot slot
static long IHomeType = 0;         // 0 = SpringBoard's own

static IMP IOrigInsets, IOrigHomeType;

static double INum(NSDictionary *d, NSString *k, double def) {
    id v = d[k];
    return [v respondsToSelector:@selector(doubleValue)] ? [v doubleValue] : def;
}

static BOOL IHook(NSString *cls, SEL sel, BOOL meta, id block, IMP *orig) {
    Class c = NSClassFromString(cls);
    if (c && meta) c = object_getClass(c);
    Method m = c ? class_getInstanceMethod(c, sel) : NULL;
    if (!m) {
        ILOG("hook missing: %@ %s", cls, sel_getName(sel));
        return NO;
    }
    IMP old = method_setImplementation(m, imp_implementationWithBlock(block));
    if (orig) *orig = old;
    ILOG("hooked %@ %s", cls, sel_getName(sel));
    return YES;
}

static void IInstall(void) {
    IHook(@"SBUISystemApertureLayoutMetrics", @selector(sensorRegionSize), NO, ^CGSize(id self) {
        return CGSizeMake(IIslandW, IIslandH);
    }, NULL);
    IHook(@"SBUISystemApertureLayoutMetrics", @selector(minimumScreenEdgeInsets), NO, ^NSDirectionalEdgeInsets(id self) {
        NSDirectionalEdgeInsets i = ((NSDirectionalEdgeInsets (*)(id, SEL))IOrigInsets)(self, @selector(minimumScreenEdgeInsets));
        i.top = IIslandTop;
        return i;
    }, &IOrigInsets);
    IHook(@"SBUISystemApertureLayoutMetrics", @selector(interSensorRegionInWindowSpace), NO, ^CGRect(id self) {
        return CGRectMake(IScreenW / 2 - IInterW / 2, IIslandTop, IInterW, IIslandH);
    }, NULL);
    IHook(@"UISDisplaySingleRectShape", NSSelectorFromString(@"sb_displayShapeForScreenType:"), YES, ^id(id self, NSInteger type) {
        double w = MAX(IAvoidW, IIslandW);
        CGRect r = CGRectMake(IScreenW / 2 - w / 2, IIslandTop, w, IIslandH);
        ILOG("display shape for screen type %ld -> %@", (long)type, NSStringFromCGRect(r));
        id (*init)(id, SEL, CGRect) = (id (*)(id, SEL, CGRect))objc_msgSend;
        return init([NSClassFromString(@"UISDisplaySingleRectShape") alloc], @selector(initWithRect:), r);
    }, NULL);
    IHook(@"SBHDefaultIconListLayoutProvider", NSSelectorFromString(@"currentDeviceScreenType"), YES, ^unsigned long(id self) {
        unsigned long own = ((unsigned long (*)(id, SEL))IOrigHomeType)(self, NSSelectorFromString(@"currentDeviceScreenType"));
        static dispatch_once_t once;
        dispatch_once(&once, ^{ ILOG("home screen type %lu (override %ld)", own, IHomeType); });
        return IHomeType > 0 ? (unsigned long)IHomeType : own;
    }, &IOrigHomeType);
}

// Permanent pill (preference AlwaysPill, default YES): an iPhone's idle island is the black sensor housing and
// SpringBoard draws nothing there. Here a black pill in a pass-through window one level below SpringBoard's
// SystemAperture window, in its scene: the live island grows out of the same frame and covers it.
@interface A71PillWindow : UIWindow
@end
@implementation A71PillWindow
- (UIView *)hitTest:(CGPoint)p withEvent:(UIEvent *)e { return nil; }
- (BOOL)canBecomeKeyWindow { return NO; }
@end

static A71PillWindow *IPill;
static BOOL IAlwaysPill = YES;

static NSArray *IAllWindows(void) {
    SEL s = NSSelectorFromString(@"allWindowsIncludingInternalWindows:onlyVisibleWindows:");
    if ([UIWindow respondsToSelector:s])
        return ((id (*)(id, SEL, BOOL, BOOL))objc_msgSend)(UIWindow.class, s, YES, NO);
    return UIApplication.sharedApplication.windows;
}

static void IShowPill(int attempt) {
    UIWindow *aperture = nil;
    for (UIWindow *w in IAllWindows()) {
        if ([NSStringFromClass(w.class) rangeOfString:@"SystemAperture"].location != NSNotFound) {
            aperture = w;
            break;
        }
    }
    if (!aperture || !aperture.windowScene) {
        if (attempt < 30) {
            dispatch_after(dispatch_time(DISPATCH_TIME_NOW, 2 * NSEC_PER_SEC), dispatch_get_main_queue(), ^{ IShowPill(attempt + 1); });
        } else {
            ILOG("pill: no SystemAperture window after %d tries", attempt);
        }
        return;
    }
    if (!IPill) {
        IPill = [[A71PillWindow alloc] initWithWindowScene:aperture.windowScene];
        IPill.userInteractionEnabled = NO;
        IPill.backgroundColor = UIColor.clearColor;
        UIView *pill = [UIView new];
        pill.backgroundColor = UIColor.blackColor;
        pill.layer.cornerRadius = IIslandH / 2;
        pill.layer.cornerCurve = kCACornerCurveContinuous;
        [IPill addSubview:pill];
        pill.tag = 71;
    }
    CGRect b = aperture.windowScene.coordinateSpace.bounds;
    IPill.frame = b;
    [IPill viewWithTag:71].frame = CGRectMake(b.origin.x + b.size.width / 2 - IIslandW / 2, IIslandTop, IIslandW, IIslandH);
    IPill.windowLevel = aperture.windowLevel - 1;
    IPill.hidden = NO;
    ILOG("pill: %@ at level %.0f under %@", NSStringFromCGRect([IPill viewWithTag:71].frame),
         IPill.windowLevel, NSStringFromClass(aperture.class));
}

__attribute__((constructor)) static void IInit(void) {
    @autoreleasepool {
        ILog = os_log_create("org.a71.island", "tweak");
        if (strcmp(getprogname(), "SpringBoard") != 0) return;
        NSDictionary *p = [NSDictionary dictionaryWithContentsOfFile:@"/var/mobile/Library/Preferences/org.a71.island.plist"];
        if (p[@"Enabled"] && ![p[@"Enabled"] boolValue]) {
            ILOG("disabled by preference");
            return;
        }
        IScreenW = INum(p, @"ScreenWidth", IScreenW);
        IIslandW = INum(p, @"IslandWidth", IIslandW);
        IIslandH = INum(p, @"IslandHeight", IIslandH);
        IIslandTop = INum(p, @"IslandTop", IIslandTop);
        IAvoidW = INum(p, @"StatusBarAvoidWidth", IAvoidW);
        IHomeType = (long)INum(p, @"HomeScreenType", IHomeType);
        if (p[@"AlwaysPill"]) IAlwaysPill = [p[@"AlwaysPill"] boolValue];
        if (IAlwaysPill) {
            [[NSNotificationCenter defaultCenter] addObserverForName:UIApplicationDidFinishLaunchingNotification object:nil
                                                               queue:NSOperationQueue.mainQueue usingBlock:^(NSNotification *n) {
                dispatch_after(dispatch_time(DISPATCH_TIME_NOW, 3 * NSEC_PER_SEC), dispatch_get_main_queue(), ^{ IShowPill(0); });
            }];
        }
        @try {
            IInstall();
        } @catch (NSException *e) {
            ILOG("install: %@", e);
        }
        ILOG("active: pill %.2fx%.2f at %.2f pt on %.0f pt", IIslandW, IIslandH, IIslandTop, IScreenW);
    }
}
