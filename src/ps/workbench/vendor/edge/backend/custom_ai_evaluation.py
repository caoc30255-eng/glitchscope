"""Separate raw score diagnostics, screened classifications and evidence counts."""
import collections,math
from custom_ai_core import TARGETS,query,EdgeModel

def metrics(labels,predictions,scores=None):
    tp=tn=fp=fn=abstain=0
    for y,p in zip(labels,predictions):
        if p is None:abstain+=1
        elif y and p:tp+=1
        elif not y and not p:tn+=1
        elif not y and p:fp+=1
        else:fn+=1
    total=len(labels);decided=total-abstain;fail=sum(not y for y in labels)
    rates=[tp/(tp+fn) if tp+fn else None,tn/(tn+fp) if tn+fp else None]
    estimated=[] if scores is None else [(y,s) for y,s in zip(labels,scores) if s is not None]
    return dict(total=total,decided=decided,abstain=abstain,coverage=decided/total if total else None,
        TP=tp,TN=tn,FP_false_PASS=fp,FN_false_FAIL=fn,accuracy=(tp+tn)/decided if decided else None,
        balanced_accuracy=sum(rates)/2 if None not in rates else None,
        failure_detection_fraction_all_failed_records=tn/fail if fail else None,
        score_coverage=len(estimated)/total if total else None,
        brier_descriptive=sum((s-int(y))**2 for y,s in estimated)/len(estimated) if estimated else None,
        abstentions_not_treated_as_failures=True,score_is_calibrated_probability=False)

def evaluate(bundle,splits,oof):
    model=EdgeModel(bundle);report={};predictions={}
    for target in TARGETS:
        target_report={};majority=sum(r['labels'][target] for r in splits['train'])>=len(splits['train'])/2
        counts={tuple(c['point']):(c['n'],c['successes']) for c in bundle['targets'][target]['cells']}
        for split in ('train','validation','historical_test'):
            rows=splits[split];labels=[r['labels'][target] for r in rows]
            outputs=[model.predict(query(target=target,**r['features'])) for r in rows]
            scores=[v['score'] for v in outputs];pred=[v['prediction'] for v in outputs]
            repeat=[]
            for r in rows:
                c=counts.get(tuple(r['features'][k] for k in ('d','s','phase','width')))
                repeat.append(None if c is None or 0<c[1]<c[0] else c[1]>0)
            by_session={}
            for session in sorted({r['session'] for r in rows}):
                ii=[i for i,r in enumerate(rows) if r['session']==session]
                by_session[session]=metrics([labels[i] for i in ii],[pred[i] for i in ii],[scores[i] for i in ii])
            target_report[split]=dict(selective=metrics(labels,pred,scores),
                raw_score_threshold_half=metrics(labels,[None if s is None else s>=.5 for s in scores],scores),
                repeat_table_baseline=metrics(labels,repeat),majority_baseline=metrics(labels,[majority]*len(rows)),
                always_fail_baseline=metrics(labels,[False]*len(rows)),by_session=by_session,
                interpretation='Retrospective public development data; not prospective hardware speedup proof')
            predictions[target+'_'+split]=[dict(uid=r['uid'],session=r['session'],features=r['features'],label=y,prediction=v) for r,y,v in zip(rows,labels,outputs)]
        cv=oof[target];labels=[r['label'] for r in cv];scores=[None if r['estimate'] is None else r['estimate']['score'] for r in cv]
        target_report['grouped_CV_raw']=metrics(labels,[None if s is None else s>=.5 for s in scores],scores)
        target_report['grouped_CV_scope']='Whole phase/width group withheld including both d values and all repeats; hull-unsupported folds abstain. Screening thresholds are trained on these OOF outputs, not independently tested here.'
        target_report['threshold_screen']=bundle['targets'][target]['screen']
        report[target]=target_report
    return dict(targets=report,training_rows=len(splits['train']),validation_rows=len(splits['validation']),historical_rows=len(splits['historical_test']),
        groupwise_splits=True,postmeasurement_features_used=False,validation_used_for_fit=False,
        historical_used_for_fit=False,prospective_generalization_proven=False,hardware_acceleration_accepted=False),predictions
