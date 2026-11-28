#include <unistd.h>

/* SPDX-License-Identifier: MIT
 * Metal libraries/functions backed by the AIR reader, without Apple's compiler
 * service or a Vulkan specialization step. Included in SweetNativeMetal.m. */
@interface SweetNativeFunction : NSObject {
@public
    id _nativeDevice;
    NSData *_nativeAIR;
    NSString *_nativeName;
    NSUInteger _nativeType;
    NSArray *_nativeConstants;
}
@end
@interface SweetNativeLibrary : NSObject {
    id _nativeDevice;
    NSData *_nativeData;
    struct rwa_library *_nativeLibrary;
    NSString *_nativeLabel;
}
- (id)initWithDevice:(id)device data:(NSData *)data error:(NSError **)error;
@end
static NSError *native_error(const char *why) {
    return [NSError errorWithDomain:@"SweetNativeMetal" code:1
        userInfo:@{NSLocalizedDescriptionKey:[NSString stringWithUTF8String:why?why:"native driver error"]}];
}
static BOOL native_method_abi(id value,SEL selector,const char *encoding) {
    Method m=class_getInstanceMethod(object_getClass(value),selector);
    return m && !strcmp(method_getTypeEncoding(m),encoding);
}
static unsigned native_constant_bytes(NSUInteger type) {
    switch(type) {
    case 3:case 29:case 33:return 4;
    case 4:case 30:case 34:return 8;
    case 16:case 37:case 41:return 2;
    case 17:case 38:case 42:return 4;
    case 18:case 39:case 43:return 6;
    case 19:case 40:case 44:return 8;
    case 45:case 49:case 53:return 1;
    case 46:case 50:case 54:return 2;
    case 47:case 51:case 55:return 3;
    case 48:case 52:case 56:return 4;
    case 81:case 85:return 8;
    default:return 0;
    }
}
@interface NSObject (SweetConstantAccess)
- (NSArray *)newIndexedConstantArray;
- (NSArray *)newNamedConstantArray;
- (NSUInteger)dataType;
- (void *)data;
- (NSUInteger)index;
@end
@implementation SweetNativeFunction
+ (void)load {
    Protocol *p=objc_getProtocol("MTLFunction");if(p)class_addProtocol(self,p);
}
- (void)dealloc {
    [_nativeDevice release];[_nativeAIR release];[_nativeName release];[_nativeConstants release];[super dealloc];
}
- (id)device {return _nativeDevice;}
- (NSString *)name {return _nativeName;}
- (NSUInteger)functionType {return _nativeType;}
- (NSData *)bitcodeData {return _nativeAIR;}
- (NSString *)label {return _nativeName;}
- (void)setLabel:(NSString *)label {(void)label;}
- (NSDictionary *)functionConstantsDictionary {return @{};}
- (NSArray *)vertexAttributes {return @[];}
- (NSArray *)stageInputAttributes {return @[];}
- (NSUInteger)patchType {return 0;}
- (NSInteger)patchControlPointCount {return 0;}
- (NSUInteger)options {return 0;}
- (id)newArgumentEncoderWithBufferIndex:(NSUInteger)index {
    return [_nativeDevice redwoodArgumentEncoderForFunction:self bufferIndex:index];
}
- (id)newArgumentEncoderWithBufferIndex:(NSUInteger)index reflection:(id *)reflection {
    if(reflection)*reflection=nil;return [self newArgumentEncoderWithBufferIndex:index];
}
@end
@implementation SweetNativeLibrary
+ (void)load {
    Protocol *p=objc_getProtocol("MTLLibrary");if(p)class_addProtocol(self,p);
}
- (id)initWithDevice:(id)device data:(NSData *)data error:(NSError **)error {
    self=[super init];if(!self)return nil;
    char why[512]={0};_nativeLibrary=rwa_library_open([data bytes],[data length],why,sizeof why);
    if(!_nativeLibrary){if(error)*error=native_error(why);[self release];return nil;}
    _nativeData=[data copy];_nativeDevice=[device retain];if(error)*error=nil;return self;
}
- (void)dealloc {
    rwa_library_close(_nativeLibrary);[_nativeData release];[_nativeDevice release];[_nativeLabel release];[super dealloc];
}
- (id)device {return _nativeDevice;}
- (NSString *)label {return _nativeLabel;}
- (void)setLabel:(NSString *)label {[_nativeLabel release];_nativeLabel=[label copy];}
- (NSUInteger)type {return 0;}
- (NSString *)installName {return nil;}
- (NSArray *)functionNames {
    NSMutableArray *names=[NSMutableArray array];
    for(unsigned i=0;i<rwa_library_count(_nativeLibrary);i++) {
        const char *n=rwa_library_name(_nativeLibrary,i);
        if(n)[names addObject:[NSString stringWithUTF8String:n]];
    }return names;
}
- (id)newFunctionWithName:(NSString *)name {
    NSError *error=nil;id f=[self newFunctionWithName:name constantValues:nil error:&error];
    if(!f)rw_print("function %s: %s\n",[name UTF8String],[[error localizedDescription] UTF8String]);return f;
}
- (id)newFunctionWithName:(NSString *)name constantValues:(id)values error:(NSError **)error {
    if(!name){if(error)*error=native_error("function name is nil");return nil;}
    unsigned found=rwa_library_count(_nativeLibrary);
    for(unsigned i=0;i<found;i++)if(!strcmp(rwa_library_name(_nativeLibrary,i),[name UTF8String])){found=i;break;}
    const void *bytes=NULL;size_t size=0;unsigned type=0;
    if(!name || rwa_library_function(_nativeLibrary,found,&bytes,&size,&type)) {
        if(error)*error=native_error("function absent or not an executable vertex/fragment/compute entrypoint");return nil;
    }
    NSMutableArray *constants=[NSMutableArray array];
    if(values) {
        if(!native_method_abi(values,sel_getUid("newIndexedConstantArray"),"@16@0:8") ||
           !native_method_abi(values,sel_getUid("newNamedConstantArray"),"@16@0:8")) {
            if(error)*error=native_error("unrecognized Metal function-constant ABI");return nil;
        }
        id snapshot=[values copy];
        NSArray *indexed=[snapshot newIndexedConstantArray],*named=[snapshot newNamedConstantArray];
        BOOL valid=YES;
        for(unsigned group=0;group<2;group++)for(id value in (group?named:indexed)) {
            if(!native_method_abi(value,@selector(dataType),"Q16@0:8") ||
               !native_method_abi(value,@selector(data),"^v16@0:8") ||
               !native_method_abi(value,group?@selector(name):@selector(index),group?"@16@0:8":"Q16@0:8")) {valid=NO;break;}
            unsigned n=native_constant_bytes([value dataType]);
            if(!n || ![value data]){valid=NO;break;}
            NSData *packed=[NSData dataWithBytes:[value data] length:n];
            id key=group?[value name]:@([value index]);
            if(!key){valid=NO;break;}
            [constants addObject:@{@"key":key,@"bytes":packed}];
        }
        [indexed release];[named release];[snapshot release];
        if(!valid){if(error)*error=native_error("unsupported constant type or value ABI (AIR limit: 64 bits)");return nil;}
    }
    SweetNativeFunction *f=[SweetNativeFunction new];f->_nativeDevice=[_nativeDevice retain];
    f->_nativeAIR=[[NSData alloc] initWithBytes:bytes length:size];f->_nativeName=[name copy];
    f->_nativeType=type;f->_nativeConstants=[constants copy];if(error)*error=nil;return f;
}
- (id)newFunctionWithName:(NSString *)name constantValues:(id)values pipelineLibrary:(id)library error:(NSError **)error {
    (void)library; /* a cache hint: VectorKit (Maps) passes one, nothing depends on it */
    return [self newFunctionWithName:name constantValues:values error:error];
}
- (void)newFunctionWithName:(NSString *)name constantValues:(id)values completionHandler:(void (^)(id,NSError *))handler {
    NSError *e=nil;id f=[self newFunctionWithName:name constantValues:values error:&e];
    if(handler)handler(f,e);[f release];
}
- (id)newFunctionWithDescriptor:(MTLFunctionDescriptor *)d error:(NSError **)e {
    return [self newFunctionWithName:d.name constantValues:d.constantValues error:e];
}
/* IconRendering (iOS 26) asks for its stitchable functions this way. */
- (void)newFunctionWithDescriptor:(MTLFunctionDescriptor *)d completionHandler:(void (^)(id,NSError *))handler {
    NSError *e=nil;id f=[self newFunctionWithDescriptor:d error:&e];
    if(handler)handler(f,e);[f release];
}
@end
/* Explicitly opt-in local capture. Never dump Apple AIR into public CI/logs.
 * Captures immutable shader/constant snapshots, not application buffer contents.
 */
static void native_capture_function(SweetNativeFunction *function,unsigned stage) {
    if(stage>=3 || access("/private/var/tmp/sweet-native-capture",F_OK))return;
    if(![function->_nativeName hasPrefix:@"fixed_"])return;
    static unsigned counts[3];
    if(counts[stage]>=16)return;
    unsigned index=counts[stage]++;
    NSString *base=[NSString stringWithFormat:@"/private/var/tmp/sweet-native-%d-%u-%u",getpid(),stage,index];
    NSMutableArray *constants=[NSMutableArray array];
    for(NSDictionary *value in function->_nativeConstants) {
        NSData *bytes=value[@"bytes"];
        [constants addObject:@{@"key":value[@"key"],@"base64":[bytes base64EncodedStringWithOptions:0]}];
    }
    NSDictionary *record=@{@"function":function->_nativeName,@"stage":@(stage),@"constants":constants};
    NSError *error=nil;
    NSData *json=[NSJSONSerialization dataWithJSONObject:record options:NSJSONWritingPrettyPrinted error:&error];
    BOOL ok=json && [function->_nativeAIR writeToFile:[base stringByAppendingString:@".air"] atomically:YES] &&
                   [json writeToFile:[base stringByAppendingString:@".json"] atomically:YES];
    rw_print("shader capture %s: %s\n",[base UTF8String],ok?"saved":"failed");
}
static BOOL native_specialize(struct rwa_device *device,id function,unsigned stage,char *why,size_t n) {
    if(!function)return rwa_set_constants(device,stage,NULL,0,why,n)==0;
    if(![function isKindOfClass:[SweetNativeFunction class]]) {
        snprintf(why,n,"pipeline function was not created by SweetNativeMetal");return NO;
    }
    native_capture_function((SweetNativeFunction *)function,stage);
    NSArray *values=((SweetNativeFunction *)function)->_nativeConstants;
    if([values count]>256){snprintf(why,n,"too many function constants");return NO;}
    struct rwa_constant packed[256]={0};unsigned i=0;
    for(NSDictionary *value in values) {
        id key=value[@"key"];NSData *bytes=value[@"bytes"];
        packed[i].bytes=(unsigned)[bytes length];memcpy(&packed[i].bits,[bytes bytes],[bytes length]);
        if([key isKindOfClass:[NSString class]])packed[i].name=[key UTF8String];
        else packed[i].index=[key unsignedIntValue];i++;
    }
    return rwa_set_constants(device,stage,packed,i,why,n)==0;
}

/*
 * A71: visible function tables (RenderBox's custom effects: IconRendering's clampToEdges_v1 and
 * friends, called from uber_fragment through air.get_function_pointer_visible_function_table).
 * A pipeline's linked functions get handles 1..n in descriptor order; a table is a buffer of
 * 8-byte handles bound at its buffer index, and the AIR translator calls the function whose
 * handle the shader loads (air_call_indirect).
 */
@interface SweetNativeFunctionHandle : NSObject {
@public
    id _function;
    id _device;
    uint64_t _handle;
}
@end
@implementation SweetNativeFunctionHandle
+ (void)load {
    Protocol *p=objc_getProtocol("MTLFunctionHandle");if(p)class_addProtocol(self,p);
}
- (void)dealloc {[_function release];[_device release];[super dealloc];}
- (NSUInteger)functionType {return 5;}
- (NSString *)name {return [_function name];}
- (id)device {return _device;}
- (uint64_t)gpuResourceID {return _handle;}
@end

@interface SweetNativeVisibleFunctionTable : NSObject {
@public
    id _device;
    id _buffer;
    NSUInteger _count;
    NSString *_label;
}
- (id)nativeBuffer;
@end
@implementation SweetNativeVisibleFunctionTable
+ (void)load {
    Protocol *p=objc_getProtocol("MTLVisibleFunctionTable");if(p)class_addProtocol(self,p);
}
- (void)dealloc {[_buffer release];[_device release];[_label release];[super dealloc];}
- (id)nativeBuffer {return _buffer;}
- (id)device {return _device;}
- (NSString *)label {return _label;}
- (void)setLabel:(NSString *)label {[_label release];_label=[label copy];}
- (uint64_t)gpuResourceID {return [_buffer respondsToSelector:@selector(gpuAddress)]?[_buffer gpuAddress]:0;}
- (NSUInteger)allocatedSize {return [_buffer length];}
- (NSUInteger)storageMode {return 0;}
- (NSUInteger)cpuCacheMode {return 0;}
- (NSUInteger)hazardTrackingMode {return 0;}
- (NSUInteger)resourceOptions {return 0;}
- (void)setFunction:(id)function atIndex:(NSUInteger)index {
    if(index>=_count)return;
    uint64_t h=[function isKindOfClass:[SweetNativeFunctionHandle class]]?((SweetNativeFunctionHandle *)function)->_handle:0;
    ((uint64_t *)[_buffer contents])[index]=h;
    static unsigned told;
    if(told++<8)rw_print("visible function table %p: slot %lu = handle %llu (%s)\n",self,(unsigned long)index,
                         (unsigned long long)h,[[function name] UTF8String]?:"nil");
}
- (void)setFunctions:(const id *)functions withRange:(NSRange)range {
    for(NSUInteger i=0;i<range.length;i++)[self setFunction:functions?functions[i]:nil atIndex:range.location+i];
}
@end

/* The linked functions of one stage, from an MTLLinkedFunctions (functions, then
 * privateFunctions), handed to the translator; returns them in handle order, or nil and
 * a reason. A descriptor without any clears the stage. */
static char native_linked_key;   /* the pipeline's handle order, an associated NSArray */
static NSArray *native_link(struct rwa_device *device,id linked,unsigned stage,char *why,size_t n) {
    NSMutableArray *order=[NSMutableArray array];
    if(linked) {
        if([linked respondsToSelector:@selector(functions)])[order addObjectsFromArray:[linked functions]?:@[]];
        if([linked respondsToSelector:@selector(privateFunctions)])[order addObjectsFromArray:[linked privateFunctions]?:@[]];
    }
    if([order count]>16){snprintf(why,n,"more than 16 linked functions (%lu)",(unsigned long)[order count]);return nil;}
    struct rwa_linked fns[16];unsigned count=0;
    for(id f in order) {
        if(![f isKindOfClass:[SweetNativeFunction class]]) {
            snprintf(why,n,"linked function %s was not created by SweetNativeMetal",[[f name] UTF8String]?:"?");return nil;
        }
        SweetNativeFunction *sf=(SweetNativeFunction *)f;
        fns[count++]=(struct rwa_linked){[sf->_nativeAIR bytes],[sf->_nativeAIR length],[sf->_nativeName UTF8String]};
    }
    if(rwa_set_linked(device,stage,fns,count,why,n))return nil;
    if(count)rw_print("pipeline stage %u links %u visible function(s), first %s\n",stage,count,fns[0].name);
    return order;
}
