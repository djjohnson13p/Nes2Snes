import copy,json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from gameplay_route import validate_actions

class TestActions(unittest.TestCase):
    def sample(self):return [dict(name='first',updates=60,buttons=['right','a'])]
    def test_accepts_and_copies(self):
        a=self.sample();b=validate_actions(a);self.assertEqual(a,b);b[0]['buttons'].append('b');self.assertNotEqual(a,b)
    def test_names(self):
        for name in ('../file','/tmp/test','x/y','x\\y','.','', 'x'*65):
            with self.subTest(name=name),self.assertRaises(ValueError):
                a=self.sample();a[0]['name']=name;validate_actions(a)
    def test_counts(self):
        for n in (True,False,-1,0,601,1.5,'60',None):
            with self.subTest(n=n),self.assertRaises(ValueError):
                a=self.sample();a[0]['updates']=n;validate_actions(a)
    def test_buttons(self):
        for b in (None,'a',['turbo'],['A'],['right','right'],['right','left'],['up','down'],[5]):
            with self.subTest(buttons=b),self.assertRaises(ValueError):
                a=self.sample();a[0]['buttons']=b;validate_actions(a)
    def test_unique(self):
        with self.assertRaises(ValueError):validate_actions(self.sample()*2)
    def test_schema(self):
        for a in ({},[],[{}],[dict(name='n',updates=1,buttons=[],extra=0)]):
            with self.assertRaises(ValueError):validate_actions(a)
    def test_total_budget(self):
        with self.assertRaises(ValueError):validate_actions([dict(name=f'a{i}',updates=600,buttons=[]) for i in range(167)])
    def test_action_budget(self):
        with self.assertRaises(ValueError):validate_actions([dict(name=f'a{i}',updates=1,buttons=[]) for i in range(513)])
    def test_stair_route(self):
        p=Path(__file__).resolve().parents[1]/'tools/routes/cv3-stair-room.json'
        a=validate_actions(json.loads(p.read_text()));self.assertEqual(len(a),57);self.assertEqual(sum(x['updates'] for x in a),3332)
